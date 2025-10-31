/**
 * Async BullMQ Worker - Submits tasks and returns immediately
 * Does NOT wait for processing - Python calls back when done
 */

require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const { Worker } = require('bullmq');
const { connection } = require('../queues/document_queue');
const MongoService = require('../services/mongo_service');
const AsyncExtractionService = require('../services/async_extraction_service');

const WORKER_CONCURRENCY = parseInt(process.env.WORKER_CONCURRENCY) || 50;

// Create worker
const worker = new Worker(
  'document_extraction',
  async (job) => {
    const { batch_id, document_type, documents, vendor_ids } = job.data;
    
    console.log(`🔄 Processing batch: ${batch_id} | Type: ${document_type} | Docs: ${documents.length}`);
    
    const mongoService = new MongoService();
    const asyncExtractionService = new AsyncExtractionService();
    
    try {
      await mongoService.connect();
      
      // Update batch status to processing
      await mongoService.updateBatchStatus(batch_id, 'submitting', {
        started_at: new Date(),
        worker_id: worker.id
      });
      
      // Initialize batch progress tracking
      await mongoService.db.collection('batches').updateOne(
        { batch_id },
        {
          $set: {
            progress: {
              completed: 0,
              successful: 0,
              failed: 0,
              errors: []
            }
          }
        }
      );
      
      // Submit all documents in batch (PARALLEL submission)
      const submissionResults = await asyncExtractionService.submitBatchAsync(
        batch_id,
        document_type,
        documents
      );
      
      const submittedCount = submissionResults.filter(r => r.submitted).length;
      const failedCount = submissionResults.filter(r => !r.submitted).length;
      
      console.log(`✅ Batch ${batch_id} submissions: ${submittedCount} submitted, ${failedCount} failed`);
      
      // Update batch status to "processing" (waiting for callbacks)
      await mongoService.updateBatchStatus(batch_id, 'processing', {
        submissions: {
          total: submissionResults.length,
          submitted: submittedCount,
          failed: failedCount
        }
      });
      
      // Mark job as complete (we're done submitting)
      return {
        batch_id,
        submitted: submittedCount,
        failed: failedCount,
        status: 'submitted'
      };
      
    } catch (error) {
      console.error(`❌ Batch ${batch_id} error:`, error.message);
      
      await mongoService.markBatchFailed(batch_id, error.message);
      
      throw error;
    }
  },
  {
    connection,
    concurrency: WORKER_CONCURRENCY,
    limiter: {
      max: 500, // Max 500 submissions per minute (matches OpenAI limit)
      duration: 60000
    }
  }
);

// Worker event handlers
worker.on('completed', (job) => {
  console.log(`✅ Job ${job.id} completed`);
});

worker.on('failed', (job, err) => {
  console.error(`❌ Job ${job?.id} failed:`, err.message);
});

worker.on('error', (err) => {
  console.error('❌ Worker error:', err);
});

console.log(`🚀 Async Worker started with concurrency: ${WORKER_CONCURRENCY}`);
console.log(`📊 Processing queue: document_extraction (Async Mode)`);
console.log(`🔄 Submissions only - callbacks handle results`);

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('Shutting down worker...');
  await worker.close();
});
