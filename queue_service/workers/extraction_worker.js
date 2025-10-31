/**
 * Stage 4: BullMQ Worker - Document Extraction
 * Processes batches of 10 documents using OpenAI GPT-4o Vision API
 */

require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const { Worker } = require('bullmq');
const { connection } = require('../queues/document_queue');
const MongoService = require('../services/mongo_service');
const ExtractionService = require('../services/extraction_service');

const WORKER_CONCURRENCY = parseInt(process.env.WORKER_CONCURRENCY) || 50;

// Create worker
const worker = new Worker(
  'document_extraction',
  async (job) => {
    const { batch_id, document_type, documents, vendor_ids } = job.data;
    
    console.log(`🔄 Processing batch: ${batch_id} | Type: ${document_type} | Docs: ${documents.length}`);
    
    const mongoService = new MongoService();
    const extractionService = new ExtractionService();
    
    try {
      await mongoService.connect();
      
      // Update batch status to processing
      await mongoService.updateBatchStatus(batch_id, 'processing', {
        started_at: new Date(),
        worker_id: worker.id
      });
      
      // Process the batch (call OpenAI API)
      const results = await extractionService.processBatch(
        document_type,
        documents,
        (progress) => {
          // Update job progress
          job.updateProgress(progress);
          mongoService.updateBatchProgress(batch_id, progress);
        }
      );
      
      // Save extracted data for each vendor
      for (let i = 0; i < results.length; i++) {
        const result = results[i];
        const vendorId = vendor_ids[i];
        
        if (result.success) {
          // Save to vendor's extracted folder
          await extractionService.saveExtractedData(
            documents[i].workspace_path,
            document_type,
            result.data
          );
          
          // Update MongoDB vendor record
          await mongoService.updateVendorExtractedData(
            vendorId,
            document_type,
            {
              ...result.data,
              confidence: result.confidence,
              extracted_at: new Date(),
              method: 'openai_gpt4o_vision'
            }
          );
        }
      }
      
      // Check if all documents for these vendors are now extracted
      await extractionService.checkAndUpdateVendorCompletionStatus(
        vendor_ids,
        mongoService
      );
      
      // Mark batch as completed
      await mongoService.markBatchCompleted(batch_id, {
        successful: results.filter(r => r.success).length,
        failed: results.filter(r => !r.success).length,
        results: results
      });
      
      console.log(`✅ Batch ${batch_id} completed: ${results.filter(r => r.success).length}/${results.length} successful`);
      
      return {
        batch_id,
        status: 'completed',
        results
      };
      
    } catch (error) {
      console.error(`❌ Error processing batch ${batch_id}:`, error);
      
      // Mark batch as failed
      await mongoService.markBatchFailed(batch_id, error.message);
      
      throw error;
    } finally {
      await mongoService.close();
    }
  },
  {
    connection,
    concurrency: WORKER_CONCURRENCY,
    limiter: {
      max: 500, // OpenAI rate limit: 500 requests per minute
      duration: 60000 // 1 minute
    }
  }
);

// Worker event listeners
worker.on('completed', (job) => {
  console.log(`✅ Job ${job.id} completed`);
});

worker.on('failed', (job, err) => {
  console.error(`❌ Job ${job.id} failed:`, err.message);
});

worker.on('error', (err) => {
  console.error('❌ Worker error:', err);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, closing worker...');
  await worker.close();
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, closing worker...');
  await worker.close();
  process.exit(0);
});

console.log(`🚀 Worker started with concurrency: ${WORKER_CONCURRENCY}`);
console.log(`📊 Processing queue: document_extraction`);
