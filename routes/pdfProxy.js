const express = require('express');
const router = express.Router();
const axios = require('axios');
const rateLimit = require('express-rate-limit');
const { URL } = require('url');
const cors = require('cors');

// Create a route-specific rate limiter
const limiter = rateLimit({
    windowMs: 5 * 60 * 1000,
    max: 50,
    message: { error: 'Too many PDF requests, please try again later' }
});

// Whitelist of allowed domains for PDF sources
const ALLOWED_DOMAINS = new Set([
    'arxiv.org',
    'papers.ssrn.com'
]);

// CORS configuration specific for PDF endpoint
const corsOptions = {
    origin: function (origin, callback) {
        // Allow requests with no origin (like mobile apps or curl requests)
        if (!origin || origin === 'null') {
            callback(null, true);
            return;
        }
        callback(null, true);
    },
    methods: ['GET', 'OPTIONS'],
    credentials: true,
    maxAge: 3600,
    exposedHeaders: ['Content-Disposition', 'Content-Length'],
    allowedHeaders: ['Content-Type', 'Authorization']
};

// Validate URL helper function
const isValidUrl = (urlString) => {
    try {
        const url = new URL(urlString);
        return ALLOWED_DOMAINS.has(url.hostname) && 
               (url.protocol === 'https:' || url.protocol === 'http:');
    } catch {
        return false;
    }
};

// Apply CORS middleware before the route handler
router.use(cors(corsOptions));

// Handle OPTIONS requests explicitly
router.options('*', cors(corsOptions));

// Apply rate limiter after CORS
router.use(limiter);

// Main proxy route
router.get('/', async (req, res) => {
    try {
        // Set CORS headers explicitly for all requests
        res.header('Access-Control-Allow-Origin', '*');
        res.header('Access-Control-Allow-Methods', 'GET, OPTIONS');
        res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
        
        const pdfUrl = req.query.url;
        
        // Input validation
        if (!pdfUrl) {
            return res.status(400).json({ error: 'PDF URL is required' });
        }

        if (!isValidUrl(pdfUrl)) {
            return res.status(403).json({ 
                error: 'Invalid URL or domain not allowed' 
            });
        }

        // Ensure we're using HTTPS
        const secureUrl = pdfUrl.replace('http://', 'https://');

        // Fetch the PDF
        const response = await axios({
            method: 'get',
            url: secureUrl,
            responseType: 'stream',
            timeout: 30000,
            maxContentLength: 50 * 1024 * 1024,
            headers: {
                'User-Agent': 'YeeFM/1.0 (https://yeefm.com)',
                'Accept': 'application/pdf'
            },
            validateStatus: (status) => status === 200
        });

        // Verify content type
        const contentType = response.headers['content-type'];
        if (!contentType || !contentType.includes('application/pdf')) {
            return res.status(400).json({ 
                error: 'Retrieved content is not a PDF' 
            });
        }

        // Set response headers
        res.setHeader('Content-Type', 'application/pdf');
        res.setHeader('Content-Disposition', 'inline; filename="paper.pdf"');
        res.setHeader('Cache-Control', 'public, max-age=3600');
        res.setHeader('X-Content-Type-Options', 'nosniff');
        
        // Stream the PDF
        response.data.on('error', (error) => {
            console.error('Stream error:', error);
            if (!res.headersSent) {
                res.status(500).json({ error: 'Error streaming PDF' });
            }
        });

        response.data.pipe(res);

    } catch (error) {
        console.error('PDF proxy error:', error);
        
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ error: 'Request timed out' });
        }
        if (error.response) {
            return res.status(error.response.status).json({ 
                error: `Remote server returned ${error.response.status}` 
            });
        }
        
        res.status(500).json({ error: 'Failed to fetch PDF' });
    }
});

module.exports = router;