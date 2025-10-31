/**
 * BullMQ Queue Service - Main Entry Point
 * Handles Stage 3 & 4 of vendor registration pipeline
 * - Stage 3: Smart Document Batching
 * - Stage 4: Parallel LLM Processing
 */

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { createBullBoard } = require('@bull-board/api');
const { BullMQAdapter } = require('@bull-board/api/bullMQAdapter');
const { ExpressAdapter } = require('@bull-board/express');

const { documentQueue } = require('./queues/document_queue');
const BatchingService = require('./services/batching_service');
const MongoService = require('./services/mongo_service');
const callbackRoutes = require('./routes/callback_routes');
const Stage3Scheduler = require('./services/stage3_scheduler');

const app = express();
const PORT = process.env.PORT || 3000;

// Initialize Stage 3 Scheduler
const stage3Scheduler = new Stage3Scheduler();

// Middleware
app.use(cors());
app.use(express.json());

// Register callback routes EARLY (before other routes)
app.use('/api/callbacks', callbackRoutes);
console.log('✅ Callback routes registered: POST /api/callbacks/ocr-result');

// Bull Board - Queue Monitoring Dashboard
const serverAdapter = new ExpressAdapter();
serverAdapter.setBasePath('/admin/queues');

createBullBoard({
  queues: [new BullMQAdapter(documentQueue)],
  serverAdapter: serverAdapter,
});

app.use('/admin/queues', serverAdapter.getRouter());

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    service: 'vendor-queue-service',
    timestamp: new Date().toISOString()
  });
});

// Queue statistics
app.get('/api/queue/stats', async (req, res) => {
  try {
    const counts = await documentQueue.getJobCounts();
    const workers = await documentQueue.getWorkers();
    
    res.json({
      queue: 'document_extraction',
      counts,
      workers: workers.length,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Trigger Stage 3 manually (for testing/maintenance)
// NOTE: In production, Stage 3 runs automatically via scheduler
app.post('/api/stage3/create-batches', async (req, res) => {
  try {
    console.log('🎯 Stage 3: Manual trigger requested...');
    
    const result = await stage3Scheduler.triggerManually();
    
    res.json({
      success: true,
      stage: 3,
      message: 'Manual batch creation completed',
      trigger_type: 'manual',
      ...result,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error creating batches:', error);
    res.status(500).json({ 
      success: false, 
      error: error.message 
    });
  }
});

// Get scheduler statistics
app.get('/api/stage3/scheduler/stats', async (req, res) => {
  try {
    const stats = await stage3Scheduler.getStatistics();
    res.json(stats);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Pause scheduler
app.post('/api/stage3/scheduler/pause', async (req, res) => {
  try {
    const result = await stage3Scheduler.pause();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Resume scheduler
app.post('/api/stage3/scheduler/resume', async (req, res) => {
  try {
    const result = await stage3Scheduler.resume();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get batch status
app.get('/api/batches/:batchId', async (req, res) => {
  try {
    const mongoService = new MongoService();
    await mongoService.connect();
    
    const batch = await mongoService.getBatchById(req.params.batchId);
    
    if (!batch) {
      return res.status(404).json({ error: 'Batch not found' });
    }
    
    res.json(batch);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get all batches with filters
app.get('/api/batches', async (req, res) => {
  try {
    const { status, document_type, limit = 50, skip = 0 } = req.query;
    
    const mongoService = new MongoService();
    await mongoService.connect();
    
    const query = {};
    if (status) query.status = status;
    if (document_type) query.document_type = document_type;
    
    const batches = await mongoService.getBatches(query, parseInt(limit), parseInt(skip));
    const total = await mongoService.getBatchesCount(query);
    
    res.json({
      batches,
      pagination: {
        total,
        limit: parseInt(limit),
        skip: parseInt(skip),
        pages: Math.ceil(total / parseInt(limit))
      }
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get processing statistics
app.get('/api/stats', async (req, res) => {
  try {
    const mongoService = new MongoService();
    await mongoService.connect();
    
    const stats = await mongoService.getProcessingStats();
    
    res.json(stats);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Retry failed batch
app.post('/api/batches/:batchId/retry', async (req, res) => {
  try {
    const mongoService = new MongoService();
    await mongoService.connect();
    
    const batch = await mongoService.getBatchById(req.params.batchId);
    
    if (!batch) {
      return res.status(404).json({ error: 'Batch not found' });
    }
    
    // Re-add to queue
    const job = await documentQueue.add(
      'extract_documents',
      batch,
      {
        attempts: 3,
        backoff: {
          type: 'exponential',
          delay: 5000
        }
      }
    );
    
    // Update batch status
    await mongoService.updateBatchStatus(batch.batch_id, 'retry_queued', {
      retry_job_id: job.id,
      retried_at: new Date()
    });
    
    res.json({
      success: true,
      message: 'Batch queued for retry',
      job_id: job.id
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Start server
app.listen(PORT, async () => {
  console.log(`🚀 BullMQ Queue Service running on port ${PORT}`);
  console.log(`📊 Queue Dashboard: http://localhost:${PORT}/admin/queues`);
  console.log(`🔍 API Docs: http://localhost:${PORT}/health`);
  
  // Initialize Stage 3 auto-scheduler
  try {
    await stage3Scheduler.initialize();
  } catch (error) {
    console.error('⚠️  Failed to initialize Stage 3 scheduler:', error.message);
    console.error('   Manual triggering still available via POST /api/stage3/create-batches');
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, closing gracefully...');
  await stage3Scheduler.shutdown();
  await documentQueue.close();
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, closing gracefully...');
  await stage3Scheduler.shutdown();
  await documentQueue.close();
  process.exit(0);
});
