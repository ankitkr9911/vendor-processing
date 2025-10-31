o/**
 * Document Extraction Service
 * Handles batch processing of documents using OpenAI GPT-4o Vision API
 * Calls Python OCR service endpoints for actual processing
 */

const axios = require('axios');
const fs = require('fs').promises;
const path = require('path');

class ExtractionService {
  constructor() {
    // Python FastAPI backend URL (where OCR service runs)
    this.pythonApiUrl = process.env.PYTHON_API_URL || 'http://localhost:8000';
  }

  /**
   * Process a batch of documents (10 documents of same type) in PARALLEL
   * Uses Promise.allSettled to send all requests simultaneously
   */
  async processBatch(documentType, documents, progressCallback) {
    const total = documents.length;
    
    try {
      console.log(`  🚀 Starting parallel processing of ${total} documents...`);
      
      // Create array of promises - all start simultaneously
      const processingPromises = documents.map((doc, index) => {
        console.log(`  📄 Submitting ${index + 1}/${total}: ${doc.document.filename}`);
        
        // Return promise for this document's processing
        return this.processDocument(documentType, doc.document.path)
          .then(result => ({
            vendor_id: doc.vendor_id,
            document_filename: doc.document.filename,
            success: true,
            data: result.data,
            confidence: result.confidence,
            error: null
          }))
          .catch(error => {
            console.error(`  ❌ Failed to process ${doc.document.filename}:`, error.message);
            return {
              vendor_id: doc.vendor_id,
              document_filename: doc.document.filename,
              success: false,
              data: null,
              confidence: 0,
              error: error.message
            };
          });
      });
      
      // Wait for ALL documents to complete (parallel execution)
      const settledResults = await Promise.allSettled(processingPromises);
      
      // Extract results from settled promises
      const results = settledResults.map((settled, index) => {
        if (settled.status === 'fulfilled') {
          return settled.value;
        } else {
          // Promise itself rejected (shouldn't happen with .catch above, but safety)
          return {
            vendor_id: documents[index].vendor_id,
            document_filename: documents[index].document.filename,
            success: false,
            data: null,
            confidence: 0,
            error: settled.reason?.message || 'Unknown error'
          };
        }
      });
      
      // Update progress to 100% after all complete
      if (progressCallback) {
        progressCallback(100);
      }
      
      const successCount = results.filter(r => r.success).length;
      console.log(`  ✅ Parallel processing complete: ${successCount}/${total} successful`);
      
      return results;
      
    } catch (error) {
      console.error('Batch processing error:', error);
      throw error;
    }
  }

  /**
   * Process a single document by calling Python OCR service
   */
  async processDocument(documentType, documentPath) {
    try {
      let endpoint;
      
      // Determine endpoint based on document type
      switch (documentType) {
        case 'aadhar':
          endpoint = '/api/ocr/process-aadhar';
          break;
        case 'pan':
          endpoint = '/api/ocr/process-pan';
          break;
        case 'gst':
          endpoint = '/api/ocr/process-gst';
          break;
        default:
          throw new Error(`Unknown document type: ${documentType}`);
      }
      
      // Call Python FastAPI endpoint with increased timeout for parallel load
      const response = await axios.post(
        `${this.pythonApiUrl}${endpoint}`,
        {
          document_path: documentPath
        },
        {
          timeout: 90000, // 90 second timeout (increased for parallel processing)
          headers: {
            'Content-Type': 'application/json'
          }
        }
      );
      
      if (response.data.success) {
        return {
          data: response.data.extracted_data,
          confidence: response.data.confidence
        };
      } else {
        throw new Error(response.data.error || 'Processing failed');
      }
      
    } catch (error) {
      if (error.response) {
        throw new Error(`API error: ${error.response.status} - ${error.response.data?.error || 'Unknown error'}`);
      } else if (error.request) {
        throw new Error('No response from Python API server');
      } else {
        throw error;
      }
    }
  }

  /**
   * Save extracted data to vendor's extracted folder
   */
  async saveExtractedData(workspacePath, documentType, data) {
    try {
      // Convert Windows path to proper format
      const extractedDir = path.join(workspacePath, 'extracted');
      
      // Ensure directory exists
      await fs.mkdir(extractedDir, { recursive: true });
      
      // Save as JSON file
      const filename = `${documentType}_data.json`;
      const filePath = path.join(extractedDir, filename);
      
      await fs.writeFile(
        filePath,
        JSON.stringify(data, null, 2),
        'utf8'
      );
      
      console.log(`  💾 Saved to: ${filePath}`);
      
      return filePath;
      
    } catch (error) {
      console.error('Error saving extracted data:', error);
      throw error;
    }
  }

  /**
   * Check if all documents (aadhar, pan, gst) are extracted for vendors
   * Update their status to "completed" if all done
   */
  async checkAndUpdateVendorCompletionStatus(vendorIds, mongoService) {
    try {
      const vendorsCollection = mongoService.db.collection('vendors');
      
      for (const vendorId of vendorIds) {
        const vendor = await vendorsCollection.findOne({ vendor_id: vendorId });
        
        if (!vendor) continue;
        
        // Check if all 3 document types have extracted_data
        const extractedData = vendor.extracted_data || {};
        
        const hasAadhar = extractedData.aadhar && Object.keys(extractedData.aadhar).length > 0;
        const hasPan = extractedData.pan && Object.keys(extractedData.pan).length > 0;
        const hasGst = extractedData.gst && Object.keys(extractedData.gst).length > 0;
        
        if (hasAadhar && hasPan && hasGst) {
          // All documents processed, mark as completed (ready for Stage 5 validation)
          await vendorsCollection.updateOne(
            { vendor_id: vendorId },
            {
              $set: {
                status: 'extraction_completed',
                extraction_completed_at: new Date(),
                updated_at: new Date()
              }
            }
          );
          
          console.log(`  ✅ Vendor ${vendorId} - All documents extracted`);
        }
      }
      
    } catch (error) {
      console.error('Error updating vendor completion status:', error);
      // Don't throw - this is not critical
    }
  }
}

module.exports = ExtractionService;
