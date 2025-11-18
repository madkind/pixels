import os
import boto3
import json
import gzip
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from .models import CanvasState, AuditLogEntry, RegionLock
from .redis_cache import redis_cache


class DynamoDBCanvas:
    def __init__(self):
        self.is_local = os.getenv("DYNAMODB_LOCAL", "false").lower() == "true"
        
        if self.is_local:
            self.dynamodb = boto3.resource(
                "dynamodb",
                endpoint_url="http://localhost:8000",
                region_name="us-west-2",
                aws_access_key_id="dummy",
                aws_secret_access_key="dummy"
            )
        else:
            self.dynamodb = boto3.resource("dynamodb")
        
        self.canvas_table = self.dynamodb.Table("pixels-canvas")
        self.audit_table = self.dynamodb.Table("pixels-audit")
        self.locks_table = self.dynamodb.Table("pixels-locks")
        
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        if self.is_local:
            try:
                self.dynamodb.create_table(
                    TableName="pixels-canvas",
                    KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST"
                )
                
                self.dynamodb.create_table(
                    TableName="pixels-audit",
                    KeySchema=[{"AttributeName": "timestamp", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "timestamp", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST"
                )
                
                self.dynamodb.create_table(
                    TableName="pixels-locks",
                    KeySchema=[{"AttributeName": "lock_id", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "lock_id", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST"
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceInUseException":
                    raise
    
    def get_canvas_state(self) -> Optional[CanvasState]:
        try:
            cached_state = redis_cache.get_canvas_state()
            if cached_state:
                return cached_state
        except Exception:
            pass
        
        try:
            response = self.canvas_table.get_item(Key={"id": "main"})
            if "Item" in response:
                item = response["Item"]
                canvas_state = CanvasState(
                    bitmap=gzip.decompress(item["bitmap"]),
                    hash=item["hash"],
                    last_updated=datetime.fromisoformat(item["last_updated"])
                )
                redis_cache.set_canvas_state(canvas_state)
                return canvas_state
        except ClientError:
            pass
        return None
    
    def save_canvas_state(self, bitmap: bytes, hash: str) -> None:
        compressed_bitmap = gzip.compress(bitmap)
        self.canvas_table.put_item(
            Item={
                "id": "main",
                "bitmap": compressed_bitmap,
                "hash": hash,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).timestamp()
            }
        )
        
        canvas_state = CanvasState(
            bitmap=bitmap,
            hash=hash,
            last_updated=datetime.now(timezone.utc)
        )
        redis_cache.set_canvas_state(canvas_state)
    
    def add_audit_entry(self, entry: AuditLogEntry) -> None:
        self.audit_table.put_item(
            Item={
                "timestamp": entry.timestamp.isoformat(),
                "user_id": entry.user_id,
                "action": entry.action,
                "details": entry.details,
                "ip_address": entry.ip_address
            }
        )
    
    def get_audit_log(self, limit: int = 100) -> List[AuditLogEntry]:
        try:
            response = self.audit_table.scan(Limit=limit)
            return [
                AuditLogEntry(
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    user_id=item.get("user_id"),
                    action=item["action"],
                    details=item["details"],
                    ip_address=item.get("ip_address")
                )
                for item in response.get("Items", [])
            ]
        except ClientError:
            return []
    
    def add_region_lock(self, lock: RegionLock) -> None:
        lock_id = f"{lock.x1},{lock.y1},{lock.x2},{lock.y2}"
        self.locks_table.put_item(
            Item={
                "lock_id": lock_id,
                "x1": lock.x1,
                "y1": lock.y1,
                "x2": lock.x2,
                "y2": lock.y2,
                "locked_by": lock.locked_by,
                "reason": lock.reason,
                "created_at": lock.created_at.isoformat()
            }
        )
    
    def remove_region_lock(self, x1: int, y1: int, x2: int, y2: int) -> None:
        lock_id = f"{x1},{y1},{x2},{y2}"
        self.locks_table.delete_item(Key={"lock_id": lock_id})
    
    def get_region_locks(self) -> List[RegionLock]:
        try:
            cached_locks = redis_cache.get_region_locks()
            if cached_locks:
                return cached_locks
        except Exception:
            pass
        
        try:
            response = self.locks_table.scan()
            locks = [
                RegionLock(
                    x1=item["x1"],
                    y1=item["y1"],
                    x2=item["x2"],
                    y2=item["y2"],
                    locked_by=item["locked_by"],
                    reason=item.get("reason"),
                    created_at=datetime.fromisoformat(item["created_at"])
                )
                for item in response.get("Items", [])
            ]
            redis_cache.set_region_locks(locks)
            return locks
        except ClientError:
            return []
    
    def is_position_locked(self, x: int, y: int) -> bool:
        locks = self.get_region_locks()
        for lock in locks:
            if lock.x1 <= x <= lock.x2 and lock.y1 <= y <= lock.y2:
                return True
        return False


dynamodb_canvas = DynamoDBCanvas()
