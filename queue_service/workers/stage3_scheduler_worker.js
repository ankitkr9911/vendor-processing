/**
 * Stage 3 Scheduler Worker
 * 
 * Processes scheduled Stage 3 batch creation jobs
 * Runs continuously in the background
 */

require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const { Worker } = require('bullmq');
const Redis = require('ioredis');
const Stage3Scheduler = require('../services/stage3_scheduler');

// Redis connection
const redisConnection = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: parseInt(process.env.REDIS_PORT) || 6379,
  password: process.env.REDIS_PASSWORD || undefined,
  maxRetriesPerRequest: null
});

// Initialize scheduler
const scheduler = new Stage3Scheduler();

// Async initialization
(async () => {
  try {
    // Initialize the repeatable cron job
    await scheduler.initialize();
  } catch (error) {
    console.error('Failed to initialize scheduler:', error);
    process.exit(1);
  }
})();

// Create worker to process scheduled jobs
const worker = new Worker(
  'stage3_scheduler',
  async (job) => {
    // Process the scheduled job
    return await scheduler.processScheduledJob(job);
  },
  {
    connection: redisConnection,
    concurrency: 1, // Process one scheduled job at a time (prevents overlapping runs)
    limiter: {
      max: 1,
      duration: 60000 // Maximum 1 job per minute (prevents burst)
    }
  }
);

// Worker event handlers
worker.on('completed', (job, result) => {
  if (result.status === 'no_work') {
    // Silent for "no work" cases to avoid log spam
    return;
  }
  
  console.log(`📊 Scheduled job ${job.id} completed:`);
  console.log(`   Status: ${result.status}`);
  console.log(`   Batches created: ${result.batches_created}`);
});

worker.on('failed', (job, err) => {
  console.error(`❌ Scheduled job ${job?.id} failed:`, err.message);
});

worker.on('error', (err) => {
  console.error('⚠️  Stage 3 scheduler worker error:', err);
});

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n🛑 SIGINT received, shutting down Stage 3 scheduler worker...');
  
  await worker.close();
  await scheduler.shutdown();
  await redisConnection.quit();
  
  console.log('✅ Stage 3 scheduler worker stopped gracefully\n');
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n🛑 SIGTERM received, shutting down Stage 3 scheduler worker...');
  
  await worker.close();
  await scheduler.shutdown();
  await redisConnection.quit();
  
  console.log('✅ Stage 3 scheduler worker stopped gracefully\n');
  process.exit(0);
});

console.log('🚀 Stage 3 Scheduler Worker started');
console.log('📅 Listening for scheduled batch creation jobs');
console.log('   Queue: stage3_scheduler');
console.log('   Concurrency: 1 (prevents overlapping runs)');
console.log('   Rate limit: 1 job per minute\n');
