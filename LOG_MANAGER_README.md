# Log Manager - SQLite Based Logging System

## Overview

The log manager has been successfully converted from JSON-based storage to SQLite database for better performance, reliability, and querying capabilities.

## Key Features

### Database Storage
- **Location**: `data/logs/bot_logs.db`
- **Format**: SQLite database
- **Schema**: Structured table with 13 columns including id, time, timestamp, level, category, message, user info, command, and details
- **Indexes**: Optimized with 5 indexes for fast querying:
  - `idx_timestamp` - For time-based queries
  - `idx_level` - For filtering by log level
  - `idx_category` - For filtering by category
  - `idx_user_id` - For user-specific queries
  - `idx_time` - For date-based queries

### Memory Cache
- Maintains recent 1000 logs in memory (deque)
- Fast access for recent log queries
- Automatically populated on startup

### Log Levels
- `INFO` - General information
- `WARNING` - Warning messages
- `ERROR` - Error messages
- `ADMIN` - Administrator actions
- `AUTO` - Automated tasks
- `SYSTEM` - System events

### Log Categories
- `콜사인` (CALLSIGN) - Callsign operations
- `대기열` (QUEUE) - Queue operations
- `동맹` (ALLIANCE) - Alliance operations
- `역할` (ROLE) - Role operations
- `예외처리` (EXCEPTION) - Exception handling
- `스케줄러` (SCHEDULER) - Scheduler tasks
- `시스템` (SYSTEM) - System events
- `관리자` (ADMIN) - Admin actions

## API Usage

### Basic Logging

```python
from log_manager import bot_logger

# System events
bot_logger.log_system_event("Bot started")

# Callsign operations
bot_logger.log_callsign("Callsign created: ABC123", user_id=123456, user_name="User1")

# Admin actions
bot_logger.log_admin_action("Config updated", user_id=999, user_name="Admin", command="/setbase")

# Errors and warnings
bot_logger.log_error("API request failed", details={"error_code": 500})
bot_logger.log_warning("Rate limit approaching")
```

### Advanced Queries

```python
from log_manager import log_manager, LogCategory
from datetime import datetime

# Get recent logs
recent_logs = log_manager.get_recent_logs(count=50)

# Get logs by category
system_logs = log_manager.get_recent_logs(count=100, category=LogCategory.SYSTEM)

# Get logs by date
today = datetime.now().strftime('%Y-%m-%d')
today_logs = log_manager.get_logs_by_date(today)

# Get user-specific logs
user_logs = log_manager.get_user_logs(user_id=123456, days=7)

# Get statistics
stats = log_manager.get_statistics()
print(f"Today: {stats['today_count']} logs")
print(f"By category: {stats['category_stats']}")

# Get total log count
total = log_manager.get_total_log_count()
```

### Export and Maintenance

```python
# Export logs to JSON
export_path = log_manager.export_logs(
    start_date='2025-12-01',
    end_date='2025-12-31',
    format='json'
)

# Export to CSV
csv_path = log_manager.export_logs(
    start_date='2025-12-01',
    end_date='2025-12-31',
    format='csv'
)

# Cleanup old logs (older than 30 days)
deleted_count = log_manager.cleanup_old_logs(days=30)
```

## Database Schema

```sql
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    timestamp REAL NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    user_id INTEGER,
    user_name TEXT,
    target_user_id INTEGER,
    target_user_name TEXT,
    command TEXT,
    details TEXT,  -- JSON string
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Performance Benefits

### SQLite vs JSON
1. **Faster Queries**: Indexed queries are much faster than JSON file scanning
2. **Concurrent Access**: SQLite handles concurrent reads/writes safely
3. **Memory Efficient**: Only loads what's needed, not entire file
4. **Scalability**: Can handle millions of log entries efficiently
5. **ACID Compliance**: Atomic, consistent, isolated, durable transactions

### Typical Query Times
- Recent logs (from cache): < 1ms
- Date-based query: 10-50ms (depending on log count)
- User-specific query: 10-50ms (indexed)
- Export operations: 100-500ms (depending on range)

## Migration from JSON

The old JSON-based logs are preserved in:
- `data/logs/bot_log_YYYY-MM-DD.json` (if they exist)

The new system uses:
- `data/logs/bot_logs.db` (SQLite database)

All existing API methods remain compatible. No code changes needed in commands.py or other modules.

## Testing

Run the test script to verify functionality:

```bash
python test_log_manager.py
```

This will:
1. Add various types of logs
2. Query logs in different ways
3. Test statistics and export
4. Verify all operations work correctly

## Integration with Discord Bot

The log manager is already integrated into your Discord bot through the global instances:

```python
from log_manager import log_manager, bot_logger

# Use bot_logger for convenience methods
bot_logger.log_callsign("message", user_id=..., user_name=...)

# Or use log_manager directly for advanced operations
from log_manager import LogLevel, LogCategory
log_manager.add_log(LogLevel.INFO, LogCategory.SYSTEM, "message", details={...})
```

## Benefits

1. **Better Performance**: SQLite is optimized for fast queries
2. **Reliability**: ACID transactions ensure data integrity
3. **Scalability**: Can handle large volumes of logs efficiently
4. **Easy Querying**: SQL-based filtering and aggregation
5. **Standard Format**: SQLite is widely supported and portable
6. **Memory Efficient**: Intelligent caching strategy
7. **Windows Compatible**: Handles Korean characters properly

## Maintenance

### Automatic Cleanup
The `cleanup_old_logs(days=30)` method:
- Deletes logs older than specified days
- Runs VACUUM to optimize database
- Returns count of deleted logs

### Database Optimization
SQLite automatically optimizes queries using indexes. The VACUUM command reclaims space after deletions.

### Backup
The database file can be backed up like any other file:
```bash
cp data/logs/bot_logs.db data/logs/bot_logs_backup_$(date +%Y%m%d).db
```

## Troubleshooting

### Database Locked
If you see "database is locked" errors, ensure:
1. Only one bot instance is running
2. Previous connections are properly closed
3. Use the context manager pattern (automatically handled)

### Performance Issues
If queries are slow:
1. Check database size: `SELECT COUNT(*) FROM logs`
2. Run cleanup: `log_manager.cleanup_old_logs(30)`
3. Check indexes: Should have 5 indexes on the logs table

### Corruption Recovery
If database becomes corrupted:
1. Stop the bot
2. Rename `bot_logs.db` to `bot_logs_corrupted.db`
3. Restart the bot (creates new database)
4. Use export functions to recover data if possible

## Future Enhancements

Potential improvements:
1. Add full-text search for log messages
2. Implement log rotation by size
3. Add log aggregation and analytics
4. Create web-based log viewer
5. Add log level filtering at runtime
6. Implement log streaming for real-time monitoring

---

**Status**: ✅ Fully implemented and tested
**Version**: 1.0 (SQLite)
**Date**: 2025-12-11
