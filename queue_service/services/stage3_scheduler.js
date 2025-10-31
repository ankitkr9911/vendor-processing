/**
 * Stage 3 Scheduler - Production-Grade Automated Batch Creation
 * 
 * Automatically triggers Stage 3 batch creation on a schedule
 * Runs independently without manual intervention
 * Efficient batching by accumulating multiple vendors before processing
 */

const { Queue } = require('bullmq');
const Redis = require('ioredis');
const BatchingService = require('./batching_service');

class Stage3Scheduler {
  constructor() {
    // Redis connection for BullMQ
    const redisConnection = new Redis({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT) || 6379,
      password: process.env.REDIS_PASSWORD || undefined,
      maxRetriesPerRequest: null
    });

    // Dedicated queue for Stage 3 scheduler
    this.schedulerQueue = new Queue('stage3_scheduler', {
      connection: redisConnection,
      defaultJobOptions: {
        attempts: 3,
        backoff: {
          type: 'exponential',
          delay: 2000
        },
        removeOnComplete: {
          age: 3600, // Keep completed jobs for 1 hour
          count: 100  // Keep last 100 completed jobs
        },
        removeOnFail: {
          age: 86400  // Keep failed jobs for 24 hours
        }
      }
    });

    // Batching service instance
    this.batchingService = new BatchingService();

    // Configuration
    this.scheduleInterval = process.env.STAGE3_SCHEDULE_INTERVAL || '*/1 * * * *'; // Default: Every 1 minute (production-ready)
    this.minVendorsForTrigger = parseInt(process.env.STAGE3_MIN_VENDORS) || 1; // Minimum vendors to trigger processing
    this.enabled = process.env.STAGE3_AUTO_ENABLED !== 'false'; // Default: enabled

    console.log('\n📅 Stage 3 Scheduler Configuration:');
    console.log(`   🔄 Schedule: ${this.scheduleInterval} (cron format)`);
    console.log(`   📊 Minimum vendors to trigger: ${this.minVendorsForTrigger}`);
    console.log(`   ✅ Auto-trigger enabled: ${this.enabled}`);
  }

  /**
   * Initialize the scheduler and add repeatable job
   */
  async initialize() {
    try {
      if (!this.enabled) {
        console.log('⏸️  Stage 3 auto-scheduler is DISABLED');
        console.log('   Set STAGE3_AUTO_ENABLED=true to enable');
        return;
      }

      // Remove any existing repeatable jobs (prevents duplicates on restart)
      const repeatableJobs = await this.schedulerQueue.getRepeatableJobs();
      for (const job of repeatableJobs) {
        await this.schedulerQueue.removeRepeatableByKey(job.key);
        console.log(`🗑️  Removed existing repeatable job: ${job.key}`);
      }

      // Add repeatable job with cron schedule
      await this.schedulerQueue.add(
        'trigger-stage3-batching',
        {
          triggeredBy: 'scheduler',
          timestamp: new Date().toISOString()
        },
        {
          repeat: {
            pattern: this.scheduleInterval,
            immediately: false // Don't run immediately on startup
          },
          jobId: 'stage3-auto-trigger' // Unique ID for this repeatable job
        }
      );

      console.log('✅ Stage 3 auto-scheduler initialized successfully');
      console.log(`   Next run: ${this.getNextRunTime()}`);
      console.log('   Scheduler will automatically create batches for ready vendors\n');

      return true;

    } catch (error) {
      console.error('❌ Failed to initialize Stage 3 scheduler:', error);
      throw error;
    }
  }

  /**
   * Process the scheduled Stage 3 job
   * This is called automatically by BullMQ on schedule
   */
  async processScheduledJob(job) {
    const startTime = Date.now();
    
    try {
      console.log('\n⏰ Stage 3 Scheduled Job Triggered');
      console.log(`   Job ID: ${job.id}`);
      console.log(`   Triggered at: ${new Date().toISOString()}`);

      // Execute Stage 3 batching logic
      const result = await this.batchingService.createBatchesFromReadyVendors();

      const processingTime = Date.now() - startTime;

      // Check if any work was done
      if (result.batches_created === 0) {
        console.log(`   📭 No vendors ready for extraction (checked in ${processingTime}ms)`);
        return {
          status: 'no_work',
          vendors_found: result.vendors_found,
          batches_created: 0,
          processing_time_ms: processingTime
        };
      }

      // Successful batch creation
      console.log(`   ✅ Stage 3 completed successfully:`);
      console.log(`      📦 Vendors found: ${result.vendors_found}`);
      console.log(`      📊 Batches created: ${result.batches_created}`);
      console.log(`      ⚡ Processing time: ${processingTime}ms`);
      console.log(`      🎯 Next run: ${this.getNextRunTime()}\n`);

      return {
        status: 'success',
        vendors_found: result.vendors_found,
        batches_created: result.batches_created,
        jobs_queued: result.jobs_queued,
        processing_time_ms: processingTime
      };

    } catch (error) {
      const processingTime = Date.now() - startTime;
      console.error(`   ❌ Stage 3 scheduled job failed (${processingTime}ms):`, error.message);
      
      throw error; // Let BullMQ handle retry
    }
  }

  /**
   * Get next scheduled run time (for display purposes)
   */
  getNextRunTime() {
    const parser = require('cron-parser');
    try {
      const interval = parser.parseExpression(this.scheduleInterval);
      return interval.next().toString();
    } catch (error) {
      return 'Unable to calculate';
    }
  }

  /**
   * Trigger Stage 3 manually (for testing or manual intervention)
   */
  async triggerManually() {
    try {
      console.log('\n🔧 Manual Stage 3 Trigger');
      
      const result = await this.batchingService.createBatchesFromReadyVendors();
      
      console.log('✅ Manual trigger completed');
      console.log(`   Vendors found: ${result.vendors_found}`);
      console.log(`   Batches created: ${result.batches_created}\n`);

      return result;

    } catch (error) {
      console.error('❌ Manual trigger failed:', error);
      throw error;
    }
  }

  /**
   * Get scheduler statistics
   */
  async getStatistics() {
    try {
      const repeatableJobs = await this.schedulerQueue.getRepeatableJobs();
      const completedCount = await this.schedulerQueue.getCompletedCount();
      const failedCount = await this.schedulerQueue.getFailedCount();
      const waitingCount = await this.schedulerQueue.getWaitingCount();

      return {
        enabled: this.enabled,
        schedule: this.scheduleInterval,
        next_run: this.getNextRunTime(),
        repeatable_jobs: repeatableJobs.length,
        stats: {
          completed: completedCount,
          failed: failedCount,
          waiting: waitingCount
        }
      };

    } catch (error) {
      console.error('Error getting scheduler statistics:', error);
      return { error: error.message };
    }
  }

  /**
   * Pause the scheduler (stops creating new batches)
   */
  async pause() {
    try {
      await this.schedulerQueue.pause();
      console.log('⏸️  Stage 3 scheduler paused');
      return { status: 'paused' };
    } catch (error) {
      console.error('Error pausing scheduler:', error);
      throw error;
    }
  }

  /**
   * Resume the scheduler
   */
  async resume() {
    try {
      await this.schedulerQueue.resume();
      console.log('▶️  Stage 3 scheduler resumed');
      return { status: 'resumed' };
    } catch (error) {
      console.error('Error resuming scheduler:', error);
      throw error;
    }
  }

  /**
   * Stop the scheduler and clean up
   */
  async shutdown() {
    try {
      console.log('\n🛑 Shutting down Stage 3 scheduler...');
      
      // Remove repeatable jobs
      const repeatableJobs = await this.schedulerQueue.getRepeatableJobs();
      for (const job of repeatableJobs) {
        await this.schedulerQueue.removeRepeatableByKey(job.key);
      }

      await this.schedulerQueue.close();
      console.log('✅ Stage 3 scheduler stopped\n');

    } catch (error) {
      console.error('Error shutting down scheduler:', error);
    }
  }
}

module.exports = Stage3Scheduler;
