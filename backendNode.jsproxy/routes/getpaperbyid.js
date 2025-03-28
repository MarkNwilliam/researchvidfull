const express = require('express');
const fetch = (...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args)); // dynamic import
const router = express.Router();

// Route to fetch Arxiv papers by id_list
router.get('/api/arxiv/papers/byId', async (req, res) => {
    const { id_list } = req.query;

    // Validate the 'id_list' query parameter
    if (!id_list) {
        return res.status(400).send("Missing required query parameter 'id_list'.");
    }

    try {
        // Fetch data from Arxiv API
        const response = await fetch(`http://export.arxiv.org/api/query?id_list=${encodeURIComponent(id_list)}`);

        // Parse the response as text (Arxiv API returns XML by default)
        const data = await response.text();

        // Return the Arxiv API response to the client
        res.status(200).send(data);
    } catch (error) {
        console.error("Error fetching from Arxiv API using id_list:", error);
        res.status(500).send("Error fetching data from Arxiv API");
    }
});

module.exports = router;