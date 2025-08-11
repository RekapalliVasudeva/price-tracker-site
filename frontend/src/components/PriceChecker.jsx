import React, { useState } from 'react';

export default function PriceChecker() {
  const [url, setUrl] = useState('');
  const [price, setPrice] = useState(null);
  const [loading, setLoading] = useState(false);

  const checkPrice = async () => {
    if (!url.trim()) return alert('Please enter a product URL.');
    setLoading(true);
    setPrice(null);
    try {
      const res = await fetch(`http://localhost:5000/check-price/?product_url=${encodeURIComponent(url)}`);
      const data = await res.json();
      setPrice(data.price || 'No price found');
    } catch (err) {
      alert('Error fetching price.');
    }
    setLoading(false);
  };

  return (
    <div className="checker-container">
      <input
        type="text"
        placeholder="Enter product URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button onClick={checkPrice} disabled={loading}>
        {loading ? 'Checking...' : 'Check Price'}
      </button>
      {price && <p className="price-output">💵 Price: {price}</p>}
    </div>
  );
}
