/**
 * MongoDB Service
 * Handles all database operations for batch processing
 */

const { MongoClient } = require('mongodb');

class MongoService {
  constructor() {
    this.client = null;
    this.db = null;
    this.uri = process.env.MONGO_URI;
    
    if (!this.uri) {
      throw new Error('MONGO_URI environment variable is required');
    }
  }

  async connect() {
    if (this.client && this.db) {
      return this.db;
    }
    
    try {
      this.client = new MongoClient(this.uri);
      await this.client.connect();
      
      // Extract database name from URI
      const dbName = this.uri.split('/').pop().split('?')[0];
      this.db = this.client.db(dbName);
      
      console.log('✅ Connected to MongoDB');
      
      return this.db;
    } catch (error) {
      console.error('❌ MongoDB connection error:', error);
      throw error;
    }
  }

  async close() {
    if (this.client) {
      await this.client.close();
      this.client = null;
      this.db = null;
    }
  }

  // ===== Vendor Operations =====

  async getVendorsReadyForExtraction() {
    const collection = this.db.collection('vendors');
    
    const vendors = await collection.find({
      status: 'ready_for_extraction'
    }).toArray();
    
    return vendors;
  }

  async updateVendorsStatus(vendorIds, status, additionalData = {}) {
    const collection = this.db.collection('vendors');
    
    const result = await collection.updateMany(
      { vendor_id: { $in: vendorIds } },
      {
        $set: {
          status: status,
          updated_at: new Date(),
          ...additionalData
        }
      }
    );
    
    return result;
  }

  async updateVendorExtractedData(vendorId, docType, extractedData) {
    const collection = this.db.collection('vendors');
    
    const updateField = `extracted_data.${docType}`;
    
    const result = await collection.updateOne(
      { vendor_id: vendorId },
      {
        $set: {
          [updateField]: extractedData,
          updated_at: new Date()
        }
      }
    );
    
    return result;
  }

  // ===== Batch Operations =====

  async insertBatches(batches) {
    const collection = this.db.collection('batches');
    
    const result = await collection.insertMany(batches);
    
    return result;
  }

  async getBatchById(batchId) {
    const collection = this.db.collection('batches');
    
    const batch = await collection.findOne({ batch_id: batchId });
    
    return batch;
  }

  async getBatches(query = {}, limit = 50, skip = 0) {
    const collection = this.db.collection('batches');
    
    const batches = await collection
      .find(query)
      .sort({ created_at: -1 })
      .limit(limit)
      .skip(skip)
      .toArray();
    
    return batches;
  }

  async getBatchesCount(query = {}) {
    const collection = this.db.collection('batches');
    
    const count = await collection.countDocuments(query);
    
    return count;
  }

  async updateBatchJobId(batchId, jobId) {
    const collection = this.db.collection('batches');
    
    const result = await collection.updateOne(
      { batch_id: batchId },
      {
        $set: {
          job_id: jobId,
          updated_at: new Date()
        }
      }
    );
    
    return result;
  }

  async updateBatchStatus(batchId, status, additionalData = {}) {
    const collection = this.db.collection('batches');
    
    const result = await collection.updateOne(
      { batch_id: batchId },
      {
        $set: {
          status: status,
          updated_at: new Date(),
          ...additionalData
        }
      }
    );
    
    return result;
  }

  async updateBatchProgress(batchId, progress, updates = null) {
    const collection = this.db.collection('batches');
    
    let updateOps = {
      updated_at: new Date()
    };
    
    // If progress is a number, set it directly
    if (typeof progress === 'number') {
      updateOps.progress = progress;
    }
    
    // Handle incremental updates using MongoDB operators
    let mongoUpdate = { $set: updateOps };
    
    if (updates) {
      // Support for $inc, $push, etc.
      if (updates.completed) mongoUpdate.$inc = { ...mongoUpdate.$inc, 'progress.completed': updates.completed.$inc };
      if (updates.successful) mongoUpdate.$inc = { ...mongoUpdate.$inc, 'progress.successful': updates.successful.$inc };
      if (updates.failed) mongoUpdate.$inc = { ...mongoUpdate.$inc, 'progress.failed': updates.failed.$inc };
      if (updates.errors) mongoUpdate.$push = { 'progress.errors': updates.errors.$push };
    }
    
    const dbResult = await collection.updateOne(
      { batch_id: batchId },
      mongoUpdate
    );
    
    return dbResult;
  }

  async markBatchCompleted(batchId, result) {
    const collection = this.db.collection('batches');
    
    const dbResult = await collection.updateOne(
      { batch_id: batchId },
      {
        $set: {
          status: 'completed',
          progress: 100,
          result: result,
          completed_at: new Date(),
          updated_at: new Date()
        }
      }
    );
    
    return dbResult;
  }

  async markBatchFailed(batchId, error) {
    const collection = this.db.collection('batches');
    
    const result = await collection.updateOne(
      { batch_id: batchId },
      {
        $set: {
          status: 'failed',
          error: error,
          failed_at: new Date(),
          updated_at: new Date()
        }
      }
    );
    
    return result;
  }

  // ===== Statistics =====

  async getProcessingStats() {
    const batchesCollection = this.db.collection('batches');
    const vendorsCollection = this.db.collection('vendors');
    
    const [
      totalBatches,
      pendingBatches,
      processingBatches,
      completedBatches,
      failedBatches,
      totalVendors,
      readyVendors,
      processingVendors,
      completedVendors
    ] = await Promise.all([
      batchesCollection.countDocuments({}),
      batchesCollection.countDocuments({ status: 'pending' }),
      batchesCollection.countDocuments({ status: 'processing' }),
      batchesCollection.countDocuments({ status: 'completed' }),
      batchesCollection.countDocuments({ status: 'failed' }),
      vendorsCollection.countDocuments({}),
      vendorsCollection.countDocuments({ status: 'ready_for_extraction' }),
      vendorsCollection.countDocuments({ status: 'processing' }),
      vendorsCollection.countDocuments({ status: 'completed' })
    ]);
    
    return {
      batches: {
        total: totalBatches,
        pending: pendingBatches,
        processing: processingBatches,
        completed: completedBatches,
        failed: failedBatches
      },
      vendors: {
        total: totalVendors,
        ready_for_extraction: readyVendors,
        processing: processingVendors,
        completed: completedVendors
      },
      timestamp: new Date().toISOString()
    };
  }
}

module.exports = MongoService;
