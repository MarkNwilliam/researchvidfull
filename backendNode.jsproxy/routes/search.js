const express = require('express');
const router = express.Router();
const fetch = (...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args));

router.get('/', async (req, res) => {
    const { 
        query: searchQuery, 
        page = '1', 
        perPage = '10', 
        sort = 'relevance' 
    } = req.query;

    // Convert to numbers
    const currentPage = Math.max(1, parseInt(page));
    const resultsPerPage = Math.min(100, Math.max(1, parseInt(perPage)));
    const startIndex = (currentPage - 1) * resultsPerPage;

    // Validate parameters
    if (!searchQuery) return res.status(400).json({ error: "Search query required" });
    if (!['relevance', 'lastUpdatedDate'].includes(sort)) {
        return res.status(400).json({ error: "Invalid sort parameter" });
    }

    try {
        const apiUrl = new URL('http://export.arxiv.org/api/query');
        apiUrl.searchParams.append('search_query', searchQuery);
        apiUrl.searchParams.append('start', startIndex);
        apiUrl.searchParams.append('max_results', resultsPerPage);
        apiUrl.searchParams.append('sortBy', sort);

        const response = await fetch(apiUrl);
        if (!response.ok) throw new Error(`arXiv API Error: ${response.status}`);
        
        const xmlData = await response.text();
        res.type('application/xml').send(xmlData);

    } catch (error) {
        console.error('API Error:', error);
        res.status(500).json({ 
            error: 'Failed to fetch results',
            message: error.message 
        });
    }
});

module.exports = router;