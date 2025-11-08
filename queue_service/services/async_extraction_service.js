/**
 * Async Extraction Service with Callback Pattern
 * Submits tasks to Python and returns immediately
 * Python calls back when processing is complete
 */

const axios = require('axios');
const Redis = require('ioredis');
const { v4: uuidv4 } = require('uuid');

class AsyncExtractionService {
  constructor() {
    this.pythonApiUrl = process.env.PYTHON_API_URL || 'http://localhost:8000';
    this.callbackUrl = process.env.QUEUE_SERVICE_URL || 'http://localhost:3005';
    
    console.log(`🔗 Callback URL configured: ${this.callbackUrl}/api/callbacks/ocr-result`);
    
    // Redis for task tracking
    this.redis = new Redis({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT) || 6379,
      password: process.env.REDIS_PASSWORD || undefined
    });
  }

  /**
   * Process a batch by submitting all documents in PARALLEL
   * Returns immediately after all submissions (doesn't wait for processing)
   */
  async submitBatchAsync(batch_id, documentType, documents) {
    const total = documents.length;
    
    try {
      console.log(`  🚀 Starting parallel async submission of ${total} documents...`);
      
      // Create array of promises - all submit simultaneously
      const submissionPromises = documents.map((doc, index) => {
        const task_id = `${batch_id}_${index}_${uuidv4().split('-')[0]}`;
        
        console.log(`  📤 Submitting ${index + 1}/${total}: ${doc.document.filename} | Task: ${task_id}`);
        
        // Return promise for this document's submission
        return this.submitTaskAsync(
          task_id,
          batch_id,
          doc.vendor_id,
          documentType,
          doc.document.path,
          doc.workspace_path
        )
          .then(() => ({
            vendor_id: doc.vendor_id,
            document_filename: doc.document.filename,
            task_id: task_id,
            submitted: true,
            error: null
          }))
          .catch(error => {
            console.error(`  ❌ Failed to submit ${doc.document.filename}:`, error.message);
            return {
              vendor_id: doc.vendor_id,
              document_filename: doc.document.filename,
              task_id: task_id,
              submitted: false,
              error: error.message
            };
          });
      });
      
      // Wait for ALL submissions to complete (parallel execution)
      const settledResults = await Promise.allSettled(submissionPromises);
      
      // Extract results from settled promises
      const results = settledResults.map((settled, index) => {
        if (settled.status === 'fulfilled') {
          return settled.value;
        } else {
          return {
            vendor_id: documents[index].vendor_id,
            document_filename: documents[index].document.filename,
            task_id: `${batch_id}_${index}_error`,
            submitted: false,
            error: settled.reason?.message || 'Unknown error'
          };
        }
      });
      
      const successCount = results.filter(r => r.submitted).length;
      console.log(`  ✅ Parallel submission complete: ${successCount}/${total} submitted`);
      
      return results;
      
    } catch (error) {
      console.error('Batch submission error:', error);
      throw error;
    }
  }

  /**
   * Submit a single task to Python async endpoint
   */
  async submitTaskAsync(task_id, batch_id, vendor_id, documentType, documentPath, workspacePath) {
    try {
      // Store task context in Redis (for callback handler)
      const taskContext = {
        batch_id,
        vendor_id,
        document_type: documentType,
        workspace_path: workspacePath,
        created_at: new Date().toISOString()
      };
      
      await this.redis.setex(
        `ocr_task:${task_id}`,
        3600, // 1 hour expiry
        JSON.stringify(taskContext)
      );
      
      // Determine endpoint based on document type
      let endpoint;
      switch (documentType) {
        case 'aadhar':
          endpoint = '/api/ocr/async/process-aadhar';
          break;
        case 'pan':
          endpoint = '/api/ocr/async/process-pan';
          break;
        case 'gst':
          endpoint = '/api/ocr/async/process-gst';
          break;
        default:
          throw new Error(`Unknown document type: ${documentType}`);
      }
      
      // Submit task to Python (expect 202 Accepted)
      const startTime = Date.now();
      const response = await axios.post(
        `${this.pythonApiUrl}${endpoint}`,
        {
          document_path: documentPath,
          task_id: task_id,
          callback_url: `${this.callbackUrl}/api/callbacks/ocr-result`
        },
        {
          timeout: 45000, // 45 second timeout - increased for burst scenarios
          headers: {
            'Content-Type': 'application/json'
          }
        }
      );
      
      const submissionTime = Date.now() - startTime;
      if (submissionTime > 5000) {
        console.warn(`    ⚠️  Slow submission (${submissionTime}ms): ${task_id}`);
      }
      
      if (response.status === 202) {
        console.log(`    ✅ Task submitted: ${task_id}`);
        return true;
      } else {
        throw new Error(`Unexpected status: ${response.status}`);
      }
      
    } catch (error) {
      // DO NOT delete Redis context - Python might still receive and process the request
      // Let Redis TTL (1 hour) handle cleanup naturally
      console.error(`    ❌ Submission failed but context preserved: ${task_id}`);
      
      if (error.response) {
        throw new Error(`API error: ${error.response.status} - ${error.response.data?.detail || 'Unknown error'}`);
      } else if (error.request) {
        throw new Error('No response from Python API server');
      } else {
        throw error;
      }
    }
  }
}

module.exports = AsyncExtractionService;
