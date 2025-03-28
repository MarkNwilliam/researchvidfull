const express = require('express');
const router = express.Router();
const axios = require('axios');
const { PassThrough } = require('stream');

router.get('/videos/:quality/:filename', async (req, res) => {
  try {
    const { quality, filename } = req.params;
    const vmUrl = `http://20.9.234.187:3000/media/videos/${quality}/${filename}`;

    // Stream the video directly from VM
    const response = await axios({
      method: 'get',
      url: vmUrl,
      responseType: 'stream',
      timeout: 3000000 // Set a timeout to avoid hanging requests
    });

    // Set proper headers for streaming
    res.set({
      'Content-Type': response.headers['content-type'],
      'Content-Length': response.headers['content-length'],
      'Cache-Control': 'no-cache', // Disable caching for faster delivery
      'Transfer-Encoding': 'chunked', // Enable chunked transfer for streaming
      'Connection': 'keep-alive'
    });

    // Use PassThrough to pipe the stream immediately
    const passThrough = new PassThrough();
    response.data.pipe(passThrough).pipe(res);

    // Handle stream errors
    passThrough.on('error', (streamError) => {
      console.error('[Stream Error]', streamError.message);
      res.status(500).json({
        status: 'stream_error',
        message: 'Error occurred while streaming video'
      });
    });

  } catch (error) {
    console.error('[Media Proxy Error]', error.message);
    res.status(error.response?.status || 500).json({
      status: 'proxy_error',
      message: 'Failed to stream video content',
      vm_error: error.response?.data || 'connection_failed'
    });
  }
});

module.exports = router;