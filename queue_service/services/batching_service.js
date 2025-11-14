/**
 * Stage 3: Smart Document Batching Service
 * Groups documents by type and creates BullMQ jobs
 */

const MongoService = require('./mongo_service');
const { documentQueue } = require('../queues/document_queue');
const { v4: uuidv4 } = require('uuid');
const path = require('path');

class BatchingService {
  constructor() {
    this.mongoService = new MongoService();
    this.BATCH_SIZE = parseInt(process.env.BATCH_SIZE) || 10;
    
    // Backend path for Docker: /app (working directory in container)
    this.BACKEND_PATH = process.env.BACKEND_PATH || process.cwd();
    
    console.log(`📁 Backend path: ${this.BACKEND_PATH}`);
  }

  /**
   * Main Stage 3 function: Create batches from vendors ready for extraction
   */
  async createBatchesFromReadyVendors() {
    try {
      await this.mongoService.connect();
      
      console.log('🔍 Finding vendors with status "ready_for_extraction"...');
      
      // Get all vendors ready for extraction
      const vendors = await this.mongoService.getVendorsReadyForExtraction();
      
      if (vendors.length === 0) {
        return {
          total_vendors: 0,
          total_documents: 0,
          batches_created: 0,
          message: 'No vendors ready for extraction'
        };
      }
      
      console.log(`📦 Found ${vendors.length} vendors ready for processing`);
      
      // Group documents by type
      const documentsByType = this.groupDocumentsByType(vendors);
      
      // Create batches for each document type
      const batches = this.createBatches(documentsByType);
      
      // Save batches to MongoDB
      await this.saveBatchesToMongo(batches);
      
      // Add batches to BullMQ queue
      const jobsAdded = await this.addBatchesToQueue(batches);
      
      // Update vendor statuses to "processing"
      const vendorIds = vendors.map(v => v.vendor_id);
      await this.mongoService.updateVendorsStatus(vendorIds, 'processing');
      
      console.log(`✅ Stage 3 Complete: ${batches.length} batches created and queued`);
      
      return {
        total_vendors: vendors.length,
        total_documents: documentsByType.aadhar.length + documentsByType.pan.length + documentsByType.gst.length,
        batches_created: batches.length,
        batches_by_type: {
          aadhar: Math.ceil(documentsByType.aadhar.length / this.BATCH_SIZE),
          pan: Math.ceil(documentsByType.pan.length / this.BATCH_SIZE),
          gst: Math.ceil(documentsByType.gst.length / this.BATCH_SIZE)
        },
        jobs_queued: jobsAdded
      };
      
    } catch (error) {
      console.error('❌ Error in createBatchesFromReadyVendors:', error);
      throw error;
    }
  }

  /**
   * Group documents by type (aadhar, pan, gst, catalogue)
   * NOW INCLUDES catalogue for AI processing
   */
  groupDocumentsByType(vendors) {
    const grouped = {
      aadhar: [],
      pan: [],
      gst: [],
      catalogue: []  // ✅ ADD catalogue to batching
    };
    
    for (const vendor of vendors) {
      const documents = vendor.documents || [];
      
      for (const doc of documents) {
        let docType = doc.type.toLowerCase();
        
        // ✅ INCLUDE catalogue for AI processing (removed skip logic)
        // Handle spelling variations: catalog → catalogue
        if (docType === 'catalog') {
          docType = 'catalogue';
        }
        
        // Handle spelling variations: aadhaar → aadhar
        if (docType === 'aadhaar') {
          docType = 'aadhar';
        }
        
        if (grouped[docType]) {
          // Convert relative path to absolute path
          const absolutePath = path.join(this.BACKEND_PATH, doc.path);
          
          grouped[docType].push({
            vendor_id: vendor.vendor_id,
            company_name: vendor.company_name,
            document: {
              ...doc,
              path: absolutePath  // Use absolute path
            },
            workspace_path: path.join(this.BACKEND_PATH, vendor.workspace_path)
          });
        }
      }
    }
    
    console.log(`📊 Documents grouped (catalogue NOW INCLUDED):`, {
      aadhar: grouped.aadhar.length,
      pan: grouped.pan.length,
      gst: grouped.gst.length,
      catalogue: grouped.catalogue.length  // ✅ Show catalogue count
    });
    
    return grouped;
  }

  /**
   * Create batches of BATCH_SIZE documents each
   */
  createBatches(documentsByType) {
    const allBatches = [];
    
    for (const [docType, documents] of Object.entries(documentsByType)) {
      if (documents.length === 0) continue;
      
      // Split into batches of BATCH_SIZE
      for (let i = 0; i < documents.length; i += this.BATCH_SIZE) {
        const batchDocuments = documents.slice(i, i + this.BATCH_SIZE);
        
        const batch = {
          batch_id: `BATCH_${docType.toUpperCase()}_${Date.now()}_${uuidv4().split('-')[0]}`,
          document_type: docType,
          documents: batchDocuments,
          vendor_ids: batchDocuments.map(d => d.vendor_id),
          total_documents: batchDocuments.length,
          status: 'pending',
          created_at: new Date(),
          priority: this.calculatePriority(docType, batchDocuments)
        };
        
        allBatches.push(batch);
      }
    }
    
    console.log(`📦 Created ${allBatches.length} batches`);
    
    return allBatches;
  }

  /**
   * Calculate batch priority (for queue ordering)
   */
  calculatePriority(docType, documents) {
    // Higher priority for smaller batches (process them first to clear queue faster)
    // Priority: 1 (highest) to 10 (lowest)
    
    const size = documents.length;
    
    if (size <= 5) return 1;
    if (size <= 7) return 3;
    return 5;
  }

  /**
   * Save batches to MongoDB for tracking
   */
  async saveBatchesToMongo(batches) {
    try {
      const batchRecords = batches.map(batch => ({
        ...batch,
        job_id: null, // Will be updated when added to queue
        progress: 0,
        result: null,
        error: null
      }));
      
      await this.mongoService.insertBatches(batchRecords);
      
      console.log(`💾 Saved ${batches.length} batches to MongoDB`);
    } catch (error) {
      console.error('❌ Error saving batches to MongoDB:', error);
      throw error;
    }
  }

  /**
   * Add batches to BullMQ queue
   */
  async addBatchesToQueue(batches) {
    try {
      const jobs = [];
      
      for (const batch of batches) {
        const job = await documentQueue.add(
          'extract_documents',
          batch,
          {
            priority: batch.priority,
            attempts: 3,
            backoff: {
              type: 'exponential',
              delay: 5000
            }
          }
        );
        
        // Update batch with job_id
        await this.mongoService.updateBatchJobId(batch.batch_id, job.id);
        
        jobs.push(job.id);
      }
      
      console.log(`✅ Added ${jobs.length} jobs to BullMQ queue`);
      
      return jobs.length;
    } catch (error) {
      console.error('❌ Error adding batches to queue:', error);
      throw error;
    }
  }
}

module.exports = BatchingService;
