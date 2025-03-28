const express = require('express');
const router = express.Router();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

router.get('/papers/byId', async (req, res) => {
  try {
    const { id_list } = req.query;
    if (!id_list) return res.status(400).json({ error: 'Missing id_list parameter' });
    
    const response = await fetch(`http://export.arxiv.org/api/query?id_list=${id_list}`);
    if (!response.ok) throw new Error(`arXiv API error: ${response.status}`);
    
    const data = await response.text();
    res.set('Content-Type', 'application/xml').send(data);
  } catch (error) {
    console.error('arXiv ID error:', error);
    res.status(500).json({ error: 'Failed to fetch paper by ID' });
  }
});

module.exports = router;