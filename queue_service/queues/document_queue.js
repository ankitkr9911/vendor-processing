/**
 * BullMQ Document Extraction Queue
 * Manages Stage 4 job processing with rate limiting
 */

const { Queue } = require('bullmq');
const Redis = require('ioredis');

// Redis connection
const connection = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: process.env.REDIS_PORT || 6379,
  password: process.env.REDIS_PASSWORD || undefined,
  maxRetriesPerRequest: null,
});

// Document extraction queue
const documentQueue = new Queue('document_extraction', {
  connection,
  defaultJobOptions: {
    attempts: 3,
    backoff: {
      type: 'exponential',
      delay: 5000, // Start with 5 seconds
    },
    removeOnComplete: {
      count: 1000, // Keep last 1000 completed jobs
      age: 24 * 3600, // Keep for 24 hours
    },
    removeOnFail: {
      count: 5000, // Keep last 5000 failed jobs for debugging
    },
  },
});

// Rate limiter settings (OpenAI: 500 RPM)
documentQueue.setGlobalConcurrency(50); // 50 concurrent workers

// Event listeners for monitoring
documentQueue.on('error', (error) => {
  console.error('❌ Queue error:', error);
});

module.exports = {
  documentQueue,
  connection,
};
