import React from 'react';
import PriceChecker from './components/PriceChecker';

export default function App() {
  return (
    <div className="app-container">
      <header>
        <h1>💰 Price Tracker</h1>
        <p>Track product prices in real-time</p>
      </header>
      <main>
        <PriceChecker />
      </main>
      <footer>
        <p>Made with ❤️ using React & FastAPI</p>
      </footer>
    </div>
  );
}
