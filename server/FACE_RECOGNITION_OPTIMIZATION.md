# Face Recognition Optimization Guide

This document provides comprehensive guidance on using the new face recognition optimization features in SmartAttend.

## Overview

SmartAttend now includes four core optimization modules:

1. **Face Embedding Cache** (`face_recognition_cache.py`) - In-memory caching with TTL
2. **Batch Face Matcher** (`batch_face_matcher.py`) - Vectorized matching operations
3. **Recognition Config** (`recognition_config.py`) - Centralized configuration
4. **Benchmark Utility** (`benchmark_faces.py`) - Performance testing

## Quick Start

### 1. Initialize Cache in Your Backend

```python
from app.services import init_cache, get_cache
from app.config import get_config, log_config

# Load configuration from environment
config = get_config()
log_config(config)

# Initialize cache
cache = init_cache(
    max_size_mb=config.CACHE_MAX_SIZE_MB,
    ttl_seconds=config.CACHE_TTL_SECONDS
)
```

### 2. Initialize Matcher

```python
from app.services import init_matcher, get_matcher

# Initialize matcher with confidence threshold
matcher = init_matcher(
    confidence_threshold=config.CONFIDENCE_THRESHOLD
)
```

### 3. Use in Your API Endpoints

```python
import numpy as np
from fastapi import APIRouter, HTTPException
from app.services import get_cache, get_matcher

router = APIRouter()

@router.post("/check-in")
async def student_check_in(student_id: str, face_embedding: list):
    """Check student in using face recognition."""
    
    # Convert to numpy array
    captured_embedding = np.array(face_embedding, dtype=np.float32)
    
    # Get all enrolled students from database
    cache = get_cache()
    matcher = get_matcher()
    
    # Try cache first
    enrolled_embedding = cache.get(student_id)
    
    if enrolled_embedding is None:
        # Cache miss - fetch from database
        enrolled_embedding = fetch_enrollment_from_db(student_id)
        if enrolled_embedding:
            cache.put(student_id, enrolled_embedding)
    
    if enrolled_embedding is None:
        raise HTTPException(status_code=404, detail="Student not enrolled")
    
    # Match with single operation
    result = matcher.match_single(
        captured_embedding,
        student_id,
        np.array(enrolled_embedding, dtype=np.float32)
    )
    
    if result.matched:
        # Record attendance
        record_attendance(student_id, "check_in", result.confidence)
        return {"status": "success", "confidence": result.confidence}
    else:
        raise HTTPException(status_code=401, detail="Face not recognized")
```

## Configuration

### Environment Variables

Create a `.env` file in the `server/` directory:

```bash
# Cache settings
CACHE_ENABLED=true
CACHE_MAX_SIZE_MB=100
CACHE_TTL_SECONDS=3600
CACHE_MAX_ENTRIES=10000

# Matching settings
CONFIDENCE_THRESHOLD=0.60
DISTANCE_METRIC=euclidean
TOP_K_MATCHES=None

# Model settings
MODEL_NAME=ArcFace
DETECTOR_BACKEND=opencv
GPU_ENABLED=false

# Edge device settings
LIGHTWEIGHT_MODEL_ENABLED=false
LIGHTWEIGHT_MODEL_NAME=OpenFace

# Performance settings
BATCH_SIZE=32
NUM_WORKERS=4
CACHE_CLEANUP_INTERVAL=300

# Monitoring
ENABLE_METRICS=true
METRICS_LOG_INTERVAL=300
```

### Configuration Priority

1. Environment variables (highest priority)
2. `.env` file
3. Hardcoded defaults (lowest priority)

## Features

### 1. Embedding Cache

The cache provides automatic TTL-based eviction and LRU eviction when size limits are exceeded.

```python
from app.services import get_cache

cache = get_cache()

# Store embedding
cache.put("student_123", embedding_array)

# Retrieve embedding
embedding = cache.get("student_123")

# Batch retrieve
embeddings = cache.batch_get(["student_1", "student_2", "student_3"])

# Get statistics
stats = cache.get_stats()
print(stats)  # Output: Hits: 150 | Misses: 50 | Hit Rate: 75.00%

# Clear cache
cache.clear()

# Clean expired entries
cache.cleanup()
```

### 2. Batch Face Matching

Process multiple faces efficiently using vectorized operations.

```python
from app.services import get_matcher
import numpy as np

matcher = get_matcher()

# Single match (typical check-in scenario)
result = matcher.match_single(
    captured_embedding,
    "student_123",
    enrolled_embedding
)

print(f"Match: {result.matched}, Confidence: {result.confidence:.4f}")

# Batch matching (search all students)
student_embeddings = {
    "student_1": np.array([...]),
    "student_2": np.array([...]),
    "student_3": np.array([...]),
}

results = matcher.match_batch(
    captured_embedding,
    student_embeddings,
    top_k=3  # Return top 3 matches
)

for result in results:
    print(f"{result.student_id}: {result.confidence:.4f} ({result.matched})")
```

### 3. Confidence Threshold

Adjustable confidence threshold to control false positive rates.

```python
matcher = get_matcher()

# Set threshold to 0.7 for stricter matching
matcher.set_confidence_threshold(0.7)

# Now only matches with confidence >= 0.7 will be positive
```

### 4. Distance Metrics

Support for both Euclidean and Cosine similarity metrics.

```python
# Euclidean distance (default)
results = matcher.match_batch(
    captured_embedding,
    student_embeddings,
    metric="euclidean"
)

# Cosine similarity
results = matcher.match_batch(
    captured_embedding,
    student_embeddings,
    metric="cosine"
)
```

## Performance Optimization

### Caching Strategy

The embedding cache is most effective when:

1. **Student enrollment is stable** - Embeddings rarely change
2. **Same students are matched repeatedly** - High cache hit rate
3. **Memory is available** - Cache can store 100-500MB+ of embeddings

**Cache Hit Rate Target**: >80% in normal classroom operation

### Batch Processing

For operations like daily attendance export or teacher dashboard:

```python
# Bad: One-by-one matching (slow)
for student_id in all_students:
    result = matcher.match_single(captured_emb, student_id, enrolled_emb)

# Good: Batch matching (fast)
student_embeddings = {s_id: get_embedding(s_id) for s_id in all_students}
results = matcher.match_batch(captured_emb, student_embeddings)
```

### Lightweight Models for Raspberry Pi

On resource-constrained devices, use lightweight models:

```bash
# In kiosk/.env
LIGHTWEIGHT_MODEL_ENABLED=true
LIGHTWEIGHT_MODEL_NAME=OpenFace
GPU_ENABLED=false
```

## Benchmarking

Run performance benchmarks to compare configurations:

```python
from app.utils.benchmark_faces import FaceRecognitionBenchmark

benchmark = FaceRecognitionBenchmark()

# Run full benchmark
results = benchmark.run_full_benchmark(
    models=["ArcFace", "Facenet"],
    detectors=["opencv", "mtcnn"]
)

# Print summary
benchmark.print_summary()

# Save results
benchmark.save_results("benchmark_results.json")
```

### Benchmark Results Example

```
ArcFace + opencv (GPU: False)
  Embedding: 45.32ms
  Match Single: 0.12ms
  Match Batch: 2.45ms
  Batch Size: 64
  Memory: 52.30MB
  Accuracy: 0.9500
```

## Monitoring & Metrics

### Cache Metrics

```python
stats = cache.get_stats()
print(f"Hit rate: {stats.hit_rate:.2f}%")
print(f"Memory usage: {stats.total_size_bytes / (1024*1024):.2f}MB")
print(f"Total evictions: {stats.evictions}")
```

### Logging

Enable detailed logging:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache logs
logger.info("Face embedding cache initialized: 100MB, TTL: 3600s")
logger.info("Cache stats: Hits: 150 | Misses: 50 | Hit Rate: 75.00%")
```

## Troubleshooting

### Low Cache Hit Rate

**Problem**: Cache hit rate is below 50%

**Solutions**:
- Increase `CACHE_MAX_SIZE_MB` to hold more embeddings
- Increase `CACHE_TTL_SECONDS` to keep entries longer
- Check if different cameras capture same student with different angles

### False Negatives (Unmatched faces)

**Problem**: Valid student faces not being matched

**Solutions**:
- Reduce `CONFIDENCE_THRESHOLD` (e.g., 0.60 → 0.50)
- Verify enrollment photos are high quality
- Check lighting conditions during check-in
- Try different distance metric (`cosine` vs `euclidean`)

### False Positives (Wrong student matched)

**Problem**: System matches wrong student

**Solutions**:
- Increase `CONFIDENCE_THRESHOLD` (e.g., 0.60 → 0.70)
- Use `top_k=1` to return only best match
- Manual review system to catch anomalies

### Memory Issues

**Problem**: Cache consuming too much memory

**Solutions**:
- Reduce `CACHE_MAX_SIZE_MB`
- Reduce `CACHE_TTL_SECONDS`
- Set `CACHE_MAX_ENTRIES` limit
- Enable periodic `cache.cleanup()`

## Integration Examples

### Flask/FastAPI Startup

```python
# app/main.py
from fastapi import FastAPI
from app.services import init_cache, init_matcher
from app.config import get_config, log_config

app = FastAPI()

@app.on_event("startup")
async def startup():
    config = get_config()
    log_config(config)
    
    if config.CACHE_ENABLED:
        init_cache(
            max_size_mb=config.CACHE_MAX_SIZE_MB,
            ttl_seconds=config.CACHE_TTL_SECONDS
        )
    
    init_matcher(confidence_threshold=config.CONFIDENCE_THRESHOLD)

@app.on_event("shutdown")
async def shutdown():
    # Optional cleanup
    cache = get_cache()
    cache.clear()
```

### Background Task for Cache Cleanup

```python
from apscheduler.schedulers.background import BackgroundScheduler
from app.services import get_cache
from app.config import get_config

def start_cache_cleanup():
    config = get_config()
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(
        get_cache().cleanup,
        'interval',
        seconds=config.CACHE_CLEANUP_INTERVAL,
        id='cache_cleanup'
    )
    
    scheduler.start()
```

## Best Practices

1. **Initialize once at startup** - Don't recreate cache/matcher repeatedly
2. **Monitor cache stats** - Log periodically to detect issues
3. **Test threshold values** - Start with 0.60, adjust based on your data
4. **Use batch operations** - When matching against multiple students
5. **Cleanup periodically** - Call `cache.cleanup()` to remove expired entries
6. **Benchmark your setup** - Test with your actual hardware/models

## References

- [DeepFace Documentation](https://github.com/serengil/deepface)
- [NumPy Broadcasting](https://numpy.org/doc/stable/user/basics.broadcasting.html)
- [Face Recognition Best Practices](https://github.com/ageitgey/face_recognition)