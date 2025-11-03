# ========================================
# Dockerfile for Queue Service (Node.js)
# BullMQ + Redis + MongoDB + Express
# ========================================

FROM node:20-slim

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (production only)
RUN npm ci --only=production && \
    npm cache clean --force

# Copy application code
COPY . .

# Expose port (Queue service runs on 3000)
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', (r) => { r.statusCode === 200 ? process.exit(0) : process.exit(1) })" || exit 1

# Run queue service
CMD ["node", "index.js"]
