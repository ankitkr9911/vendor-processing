/**
 * Callback Handler for Async OCR Processing
 * Receives results from Python service when processing completes
 */

const express = require('express');
const router = express.Router();
const Redis = require('ioredis');
const MongoService = require('../services/mongo_service');
const fs = require('fs').promises;
const path = require('path');

// Initialize Redis for task tracking
const redis = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: parseInt(process.env.REDIS_PORT) || 6379,
  password: process.env.REDIS_PASSWORD || undefined
});

const mongoService = new MongoService();

/**
 * Callback endpoint - receives OCR results from Python
 */
router.post('/ocr-result', async (req, res) => {
  const { task_id, status, extracted_data, confidence, error } = req.body;
  
  try {
    console.log(`📥 Callback received: ${task_id} | Status: ${status}`);
    
    // Retrieve task context from Redis
    const taskContextJson = await redis.get(`ocr_task:${task_id}`);
    
    if (!taskContextJson) {
      console.error(`❌ Task context not found for: ${task_id}`);
      console.log(`   This can happen if submission timed out but Python still processed`);
      console.log(`   Checking Redis keys...`);
      
      // List all task keys for debugging
      const allKeys = await redis.keys('ocr_task:*');
      console.log(`   Found ${allKeys.length} task keys in Redis`);
      
      return res.status(404).json({ 
        error: 'Task context not found',
        task_id: task_id,
        hint: 'Context may have been deleted due to submission timeout'
      });
    }
    
    const taskContext = JSON.parse(taskContextJson);
    const { batch_id, vendor_id, document_type, workspace_path } = taskContext;
    
    // Delete task from Redis (cleanup)
    await redis.del(`ocr_task:${task_id}`);
    
    // Connect to MongoDB
    await mongoService.connect();
    
    if (status === 'success') {
      // Save extracted data to file
      await saveExtractedData(workspace_path, document_type, extracted_data);
      
      // Special handling for catalogue - save to separate MongoDB collections
      if (document_type === 'catalogue') {
        await saveCatalogueToMongoDB(extracted_data, vendor_id);
      } else {
        // Update vendor record with extracted data (aadhar, pan, gst)
        await mongoService.updateVendorExtractedData(vendor_id, document_type, {
          data: extracted_data,
          confidence: confidence,
          processed_at: new Date()
        });
      }
      
      // Update batch progress
      await mongoService.updateBatchProgress(batch_id, null, {
        completed: { $inc: 1 },
        successful: { $inc: 1 }
      });
      
      console.log(`✅ Success callback processed: ${vendor_id} | ${document_type}`);
      
    } else {
      // Handle error
      console.error(`❌ Error callback: ${vendor_id} | ${document_type} | ${error}`);
      
      // Update batch progress with error
      await mongoService.updateBatchProgress(batch_id, null, {
        completed: { $inc: 1 },
        failed: { $inc: 1 },
        errors: { $push: { vendor_id, document_type, error } }
      });
    }
    
    // Check if batch is complete
    await checkBatchCompletion(batch_id);
    
    // Respond to Python
    res.status(200).json({ success: true, message: 'Callback processed' });
    
  } catch (err) {
    console.error(`💥 Callback processing error: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

/**
 * Save extracted data to vendor's extracted folder
 */
async function saveExtractedData(workspacePath, documentType, data) {
  try {
    const extractedDir = path.join(workspacePath, 'extracted');
    await fs.mkdir(extractedDir, { recursive: true });
    
    const filename = `${documentType}_data.json`;
    const filePath = path.join(extractedDir, filename);
    
    await fs.writeFile(filePath, JSON.stringify(data, null, 2), 'utf-8');
    
    console.log(`💾 Saved to: ${filePath}`);
  } catch (error) {
    console.error(`❌ Error saving extracted data: ${error.message}`);
    throw error;
  }
}

/**
 * Save catalogue data to MongoDB catalogues and products collections
 */
async function saveCatalogueToMongoDB(catalogueData, vendor_id) {
  try {
    console.log(`💾 Saving catalogue to MongoDB: ${catalogueData.catalogue_id}`);
    
    // Fetch vendor details for products
    const vendorsCollection = mongoService.db.collection('vendors');
    const vendor = await vendorsCollection.findOne({ vendor_id });
    
    if (!vendor) {
      throw new Error(`Vendor ${vendor_id} not found`);
    }
    
    const vendorDetails = {
      vendor_id: vendor.vendor_id,
      vendor_name: vendor.company_name || 'Unknown',
      location: vendor.city || 'Unknown'
    };
    
    // Extract AI summary and products from catalogue data
    const ai_summary = catalogueData.ai_summary;
    const products = catalogueData.products || [];
    
    // Remove AI summary and products from catalogue object (AI summary goes to vendor, products to separate collection)
    delete catalogueData.ai_summary;
    delete catalogueData.products;
    
    // Add catalogue_id and vendor details to all products
    products.forEach(product => {
      product.catalogue_id = catalogueData.catalogue_id;
      product.vendor = vendorDetails;
    });
    
    // Save catalogue metadata (without AI summary)
    const cataloguesCollection = mongoService.db.collection('catalogues');
    await cataloguesCollection.insertOne(catalogueData);
    console.log(`✅ Catalogue metadata saved: ${catalogueData.catalogue_id}`);
    
    // Save products with vendor details
    if (products.length > 0) {
      const productsCollection = mongoService.db.collection('products');
      await productsCollection.insertMany(products);
      console.log(`✅ ${products.length} products saved to products collection with vendor details`);
    }
    
    // Update vendor record with catalogue reference AND AI summary
    await vendorsCollection.updateOne(
      { vendor_id },
      {
        $push: {
          catalogues: {
            catalogue_id: catalogueData.catalogue_id,
            total_products: catalogueData.total_products,
            processed_at: catalogueData.processed_at
          }
        },
        $set: { 
          ai_summary: ai_summary,  // Store AI summary in vendor collection
          updated_at: new Date() 
        }
      }
    );
    
    console.log(`✅ Vendor ${vendor_id} updated with catalogue reference and AI summary`);
    
  } catch (error) {
    console.error(`❌ Error saving catalogue to MongoDB: ${error.message}`);
    throw error;
  }
}

/**
 * Check if batch is complete and update vendor status
 */
async function checkBatchCompletion(batch_id) {
  try {
    const batch = await mongoService.getBatchById(batch_id);
    
    if (!batch) return;
    
    const progress = batch.progress || { completed: 0, successful: 0, failed: 0 };
    const totalDocs = batch.total_documents;
    
    if (progress.completed >= totalDocs) {
      console.log(`✅ Batch ${batch_id} completed: ${progress.successful}/${totalDocs} successful`);
      
      // Mark batch as completed
      const finalStatus = progress.failed === 0 ? 'completed' : 'partial_success';
      await mongoService.updateBatchStatus(batch_id, finalStatus, {
        completed_at: new Date()
      });
      
      // Check vendor completion for all vendors in batch
      for (const vendor_id of batch.vendor_ids) {
        await checkVendorCompletion(vendor_id);
      }
    }
  } catch (error) {
    console.error(`Error checking batch completion: ${error.message}`);
  }
}

/**
 * Check if vendor has all documents processed (aadhar, pan, gst, and catalogue)
 */
async function checkVendorCompletion(vendor_id) {
  try {
    const vendorsCollection = mongoService.db.collection('vendors');
    const vendor = await vendorsCollection.findOne({ vendor_id });
    
    if (!vendor) return;
    
    const extractedData = vendor.extracted_data || {};
    
    // Check if all 4 document types are processed (including catalogue)
    const hasAadhar = extractedData.aadhar && extractedData.aadhar.data;
    const hasPan = extractedData.pan && extractedData.pan.data;
    const hasGst = extractedData.gst && extractedData.gst.data;
    
    // Check if catalogue is processed (catalogue is stored differently - in catalogues collection)
    const catalogues = vendor.catalogues || [];
    const hasCatalogue = catalogues.length > 0;
    
    // Vendor is complete when all 4 documents are processed
    if (hasAadhar && hasPan && hasGst && hasCatalogue) {
      await vendorsCollection.updateOne(
        { vendor_id },
        {
          $set: {
            status: 'extraction_completed',
            updated_at: new Date()
          }
        }
      );
      
      console.log(`✅ Vendor ${vendor_id} - All documents extracted (aadhar, pan, gst, catalogue)`);
    } else {
      // Log what's still pending
      const pending = [];
      if (!hasAadhar) pending.push('aadhar');
      if (!hasPan) pending.push('pan');
      if (!hasGst) pending.push('gst');
      if (!hasCatalogue) pending.push('catalogue');
      
      if (pending.length > 0) {
        console.log(`⏳ Vendor ${vendor_id} - Still processing: ${pending.join(', ')}`);
      }
    }
  } catch (error) {
    console.error(`Error checking vendor completion: ${error.message}`);
  }
}

module.exports = router;
