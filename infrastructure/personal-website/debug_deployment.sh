#!/bin/bash

echo "=== Personal Website Deployment Debug ==="
echo "Timestamp: $(date)"
echo ""

echo "=== DNS Resolution ==="
echo "www.markcheli.com: $(dig +short www.markcheli.com)"
echo "flask.markcheli.com: $(dig +short flask.markcheli.com)"
echo ""

echo "=== HTTP Connectivity Tests ==="
echo "Testing HTTP (port 80)..."
curl -I http://www.markcheli.com --connect-timeout 5 --max-time 10 2>&1 | head -5

echo ""
echo "Testing Flask API HTTP..."
curl -I http://flask.markcheli.com --connect-timeout 5 --max-time 10 2>&1 | head -5

echo ""
echo "=== HTTPS Connectivity Tests ==="
echo "Testing HTTPS (port 443)..."
curl -I https://www.markcheli.com --connect-timeout 5 --max-time 10 2>&1 | head -5

echo ""
echo "Testing Flask API HTTPS..."
curl -I https://flask.markcheli.com/health --connect-timeout 5 --max-time 10 2>&1 | head -5

echo ""
echo "=== Working Service Comparison ==="
echo "Testing existing working service..."
curl -I https://home.markcheli.com --connect-timeout 5 --max-time 10 2>&1 | head -5

echo ""
echo "=== Basic Connectivity ==="
echo "Ping test:"
ping -c 2 173.48.98.211

echo ""
echo "=== Debug Summary ==="
echo "If HTTP works but HTTPS times out: SSL certificate issue"
echo "If both HTTP and HTTPS fail: Container networking issue"
echo "If DNS doesn't resolve: DNS configuration problem"
echo "If ping fails: Network connectivity problem"