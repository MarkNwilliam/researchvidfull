const express = require('express');
const router = express.Router();
const axios = require('axios');

router.post('/', async (req, res) => {
  try {
    // Create an axios instance with 1-hour timeout (3600000 milliseconds)
    const apiClient = axios.create({
      timeout: 3600000, // 1 hour
      maxContentLength: Infinity,
      maxBodyLength: Infinity
    });

    // Forward request to VM API with extended timeout
    const vmResponse = await apiClient.post('http://20.9.234.187:3000/generate_video', req.body);

    // Rewrite video URL to use our proxy
    const originalUrl = new URL(vmResponse.data.video_url);
    const proxyPath = `${originalUrl.pathname}`;
    
    const proxiedResponse = {
      ...vmResponse.data,
      video_url: `${req.protocol}://${req.get('host')}${proxyPath}`
    };

    res.status(vmResponse.status).json(proxiedResponse);

  } catch (error) {
    // Detailed error logging
    console.error('[Video Proxy Error]', {
      message: error.message,
      code: error.code,
      stack: error.stack,
      response: error.response?.data
    });

    // Differentiate between different types of errors
    if (error.code === 'ECONNABORTED') {
      return res.status(504).json({
        status: 'timeout_error',
        message: 'Video generation service took too long to respond',
      });
    }

    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      return res.status(error.response.status).json({
        status: 'proxy_error',
        message: 'Failed to communicate with video generation service',
        vm_error: error.response.data || 'Unknown error',
        status_code: error.response.status
      });
    } else if (error.request) {
      // The request was made but no response was received
      return res.status(503).json({
        status: 'service_unavailable',
        message: 'No response received from video generation service',
      });
    }

    // Catch any other unexpected errors
    res.status(500).json({
      status: 'unexpected_error',
      message: 'An unexpected error occurred during video generation',
      error: error.message
    });
  }
});

module.exports = router;