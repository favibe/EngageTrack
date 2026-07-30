//peerjs_server.js
// Simple PeerJS signaling server
// Run this with: node peerjs_server.js

const { PeerServer } = require('peer');

const server = PeerServer({
  port: 9000,
  path: '/peerjs',
  allow_discovery: true
});

server.on('connection', (client) => {
  console.log(`✅ Peer connected: ${client.id}`);
});

server.on('disconnect', (client) => {
  console.log(`❌ Peer disconnected: ${client.id}`);
});

console.log('🚀 PeerJS Server running on port 9000');
console.log('❗ Clients should connect to: http://localhost:9000/peerjs');