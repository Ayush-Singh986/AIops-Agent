QUERIES = {
    # 1. Total request throughput across all endpoints
    "request_rate": "sum(rate(http_request_total[1m])) or vector(0)",
    
    # 2. Overall 95th percentile application response latency
    "app_p95_latency_seconds": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le)) or vector(0)",
    
    # 3. Overall rate of HTTP 5xx responses per second
    "app_error_rate": 'sum(rate(http_request_total{http_status=~"5.."}[1m])) or vector(0)',
    
    # 4. Average latency of successful Redis commands
    "redis_average_latency_seconds": "sum(rate(redis_request_duration_seconds_sum[1m])) / sum(rate(redis_request_duration_seconds_count[1m])) or vector(0)",
    
    # 5. Rate of Redis cache errors per second
    "cache_error_rate": 'sum(rate(cache_request_total{outcome="error"}[1m])) or vector(0)',
    
    # 6. Average latency of downstream catalog-service calls
    "downstream_average_latency_seconds": "sum(rate(downstream_call_duration_seconds_sum[1m])) / sum(rate(downstream_call_duration_seconds_count[1m])) or vector(0)",
    
    # 7. Rate of catalog-service errors per second
    "downstream_error_rate": 'sum(rate(downstream_calls_total{outcome="error"}[1m])) or vector(0)',
    
    # 8. Highest per-replica CPU rate (measured in cores consumed)
    "process_cpu_rate": "max(rate(process_cpu_seconds_total[1m])) or vector(0)",
    
    # 9. Highest per-replica resident memory in bytes
    "process_resident_memory_bytes": "max(process_resident_memory_bytes) or vector(0)",
    
    # 10. Availability state of all discovered app replicas (1 = all up, 0 = not all up)
    "app_availability": 'min(up{job="aiops-app"}) or vector(0)'
}