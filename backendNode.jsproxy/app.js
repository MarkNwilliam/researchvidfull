require('dotenv').config();
const express = require('express');
const cors = require('cors');
const app = express();

// Import routers
const arxivRouter = require('./routes/arxiv');
const pdfProxyRouter = require('./routes/pdfProxy');
const searchRouter = require('./routes/search');
const getPaperByIdRouter = require('./routes/getpaperbyid');
const videoProxyRouter = require('./routes/videoProxy');
const mediaProxyRouter = require('./routes/mediaProxy');

// Configure CORS to allow from anywhere
const corsOptions = {
  origin: '*', // Allow all origins
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: [
    'Content-Type',
    'Authorization',
    'X-Requested-With',
    'Accept',
    'X-Access-Token',
    'Range'
  ],
  exposedHeaders: [
    'Content-Length',
    'Content-Range',
    'X-Total-Count'
  ],
  credentials: true, // Allow cookies and auth headers
  optionsSuccessStatus: 200,
  maxAge: 86400 // 24 hour preflight cache
};

// Apply CORS middleware
app.use(cors(corsOptions));

// Handle preflight requests for all routes
app.options('*', cors(corsOptions));

// Additional manual CORS headers as backup
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header(
    'Access-Control-Allow-Headers',
    'Origin, X-Requested-With, Content-Type, Accept, Authorization, Range'
  );
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Range');
  res.header('Access-Control-Allow-Credentials', 'true');
  
  // Immediately respond to OPTIONS requests
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  next();
});

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Rate limiting configuration
const limiter = require('express-rate-limit')({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 500, // Limit each IP to 500 requests per window
  standardHeaders: true, // Return rate limit info in headers
  legacyHeaders: false, // Disable X-RateLimit-* headers
  message: {
    error: 'Too many requests from this IP, please try again later'
  }
});

// Apply routes with rate limiting
app.use('/api/arxiv', limiter, arxivRouter);
app.use('/api/getproxypdf', limiter, pdfProxyRouter);
app.use('/api/search', limiter, searchRouter);
app.use('/api/getpaperbyid', limiter, getPaperByIdRouter);
app.use('/generate_video', limiter, videoProxyRouter);
app.use('/media', limiter, mediaProxyRouter);

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({ 
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(`[${new Date().toISOString()}] Error:`, err.stack);
  
  const statusCode = err.statusCode || 500;
  const message = statusCode === 500 ? 'Internal Server Error' : err.message;
  
  res.status(statusCode).json({
    error: message,
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    path: req.path,
    method: req.method
  });
});

// Server configuration
const PORT = process.env.PORT || 3000;
const server = app.listen(PORT, () => {
  console.log(`[${new Date().toISOString()}] Server running on port ${PORT}`);
});

// Timeout and keep-alive settings
server.keepAliveTimeout = 60000; // 60 seconds
server.headersTimeout = 65000; // 65 seconds
app.timeout = 500000000; // Long timeout for video processing

// Handle shutdown gracefully
process.on('SIGTERM', () => {
  console.log('SIGTERM received. Shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});