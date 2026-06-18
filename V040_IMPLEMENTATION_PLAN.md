# Dreamdata v0.4.0 实现计划 - 用户认证与权限管理

**版本**: v0.4.0
**日期**: 2026-06-18
**状态**: 待审批

---

## 概述

v0.4.0 引入完整的用户认证与权限管理系统，支持多用户协作、细粒度权限控制和安全的密码管理。

### 用户故事映射

| ID | 用户故事 | 优先级 | 实现状态 |
|----|---------|--------|---------|
| US-001 | 初次登录创建管理员账号 | P0 | 待实现 |
| US-002 | 管理员创建普通用户 | P0 | 待实现 |
| US-003 | 管理员分配数据集权限 | P0 | 待实现 |
| US-004 | 管理员查看所有数据集和用户 | P0 | 待实现 |
| US-005 | 普通用户登录系统 | P0 | 待实现 |
| US-006 | 普通用户访问有权限的数据集 | P0 | 待实现 |
| US-007 | 普通用户创建自己的数据集（与管理员共同持有权限） | P0 | 待实现 |
| US-008 | 修改自己的密码 | P1 | 待实现 |
| US-010 | 权限级别可视化 | P1 | 待实现 |
| US-011 | 管理员创建用户时分配初始权限（可选） | P1 | 待实现 |

---

## 1. 数据库 Schema 设计

### 1.1 新增表

#### `users` - 用户表
存储用户账号信息。

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    hashed_password BYTEA NOT NULL,
    salt BYTEA NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX users_username_idx ON users(username);
CREATE INDEX users_email_idx ON users(email);
CREATE INDEX users_role_idx ON users(role);
```

#### `api_keys` - API 密钥表
为用户生成持久化的 API 密钥。

```sql
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash BYTEA NOT NULL,
    key_prefix TEXT NOT NULL,
    name TEXT,
    scopes TEXT[],
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX api_keys_user_id_idx ON api_keys(user_id);
CREATE INDEX api_keys_key_prefix_idx ON api_keys(key_prefix);
CREATE INDEX api_keys_active_idx ON api_keys(user_id, is_active) WHERE is_active = TRUE;
```

#### `dataset_permissions` - 数据集权限表
细粒度的数据集权限控制。

```sql
CREATE TABLE dataset_permissions (
    id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_level TEXT NOT NULL CHECK (permission_level IN ('owner', 'read_write', 'read_only')),
    granted_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    UNIQUE(dataset_id, user_id)
);

CREATE INDEX dataset_permissions_dataset_idx ON dataset_permissions(dataset_id);
CREATE INDEX dataset_permissions_user_idx ON dataset_permissions(user_id);
CREATE INDEX dataset_permissions_level_idx ON dataset_permissions(permission_level);
```

#### `password_reset_tokens` - 密码重置令牌表
支持密码重置功能。

```sql
CREATE TABLE password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL,
    token_prefix TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX password_reset_tokens_user_idx ON password_reset_tokens(user_id);
CREATE INDEX password_reset_tokens_prefix_idx ON password_reset_tokens(token_prefix);
```

#### `audit_log` - 审计日志表（可选，v0.4.1）
记录权限变更和关键操作。

### 1.2 迁移脚本

创建 Alembic 迁移 `0004_users_permissions.py`，包含上述所有表。

**向后兼容性考虑**：
- 现有数据不受影响
- 为已存在的 `user_annotations.user_id` 提供迁移路径（注释仍保留原始字符串 ID）
- 引入 `user_id` 映射层，兼容旧 API 的 string-based user_id

---

## 2. API 端点设计

### 2.1 认证端点 (`/auth`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/auth/setup` | 初始管理员设置（仅在无用户时可用） | 公开 |
| POST | `/auth/login` | 用户登录（返回 access token） | 公开 |
| POST | `/auth/logout` | 用户登出 | 已认证 |
| POST | `/auth/change-password` | 修改当前用户密码 | 已认证 |
| POST | `/auth/api-keys` | 生成新的 API 密钥 | 已认证 |
| GET | `/auth/api-keys` | 列出用户的 API 密钥 | 已认证 |
| DELETE | `/auth/api-keys/:id` | 撤销 API 密钥 | 已认证 |
| POST | `/auth/forgot-password` | 请求密码重置 | 公开 |
| POST | `/auth/reset-password` | 执行密码重置 | 公开 |

### 2.2 用户管理端点 (`/users`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/users` | 列出所有用户 | admin |
| POST | `/users` | 创建新用户 | admin |
| GET | `/users/:id` | 获取用户详情 | admin 或 self |
| PATCH | `/users/:id` | 更新用户信息 | admin 或 self |
| DELETE | `/users/:id` | 删除用户 | admin |
| GET | `/users/me` | 获取当前用户信息 | 已认证 |

### 2.3 权限管理端点 (`/permissions`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/permissions/datasets/:name` | 获取数据集权限列表 | owner 或 admin |
| POST | `/permissions/datasets/:name` | 分配数据集权限 | owner 或 admin |
| PATCH | `/permissions/datasets/:name/users/:id` | 更新用户权限 | owner 或 admin |
| DELETE | `/permissions/datasets/:name/users/:id` | 撤销用户权限 | owner 或 admin |
| GET | `/permissions/me/datasets` | 获取当前用户有权限的所有数据集 | 已认证 |

### 2.4 现有端点变更

所有现有端点需要：
- 使用新的认证中间件（支持 session token 和 API key）
- 在访问数据集前检查权限
- 返回 403 Forbidden 当权限不足时
- 管理员可以访问所有数据集

---

## 3. 代码结构变更

### 3.1 新增模块

```
src/dreamdata/
├── auth/
│   ├── __init__.py
│   ├── core.py              # 密码哈希、令牌生成
│   ├── models.py            # Pydantic 模型
│   ├── repository.py        # 用户/权限数据库操作
│   └── dependencies.py      # FastAPI 依赖注入
└── api/
    └── routers/
        ├── auth.py          # 认证路由
        ├── users.py         # 用户管理路由
        └── permissions.py   # 权限管理路由
```

### 3.2 核心认证逻辑 (`auth/core.py`)

- **密码哈希**: Argon2id (推荐) 或 bcrypt
- **Token 生成**: JWT (短期) + Refresh Token (长期)
- **API Key 生成**: 随机 32-byte key，前缀 `dk_`
- **安全措施**:
  - 密码最小长度 8 字符
  - API key 速率限制
  - 登录失败锁定

### 3.3 Repository 扩展 (`auth/repository.py`)

```python
@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    email: str
    role: Literal["admin", "user"]
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class DatasetPermissionRow:
    id: int
    dataset_id: int
    user_id: int
    permission_level: Literal["owner", "read_write", "read_only"]
    granted_by: int | None
    granted_at: datetime
    expires_at: datetime | None

class AuthRepository:
    def count_users(self) -> int: ...
    def create_user(
        self, *, username: str, email: str, hashed_password: bytes,
        salt: bytes, role: str
    ) -> UserRow: ...
    def get_user_by_username(self, username: str) -> UserRow | None: ...
    def get_user_by_email(self, email: str) -> UserRow | None: ...
    def get_user_by_id(self, user_id: int) -> UserRow | None: ...
    def update_user_password(self, user_id: int, hashed_password: bytes, salt: bytes) -> None: ...
    def update_last_login(self, user_id: int) -> None: ...
    def list_users(self) -> list[UserRow]: ...
    def deactivate_user(self, user_id: int) -> None: ...

    # Permission methods
    def get_dataset_permission(self, dataset_id: int, user_id: int) -> DatasetPermissionRow | None: ...
    def get_user_permissions_for_dataset(self, dataset_id: int) -> list[DatasetPermissionRow]: ...
    def get_datasets_for_user(self, user_id: int) -> list[tuple[int, str, str]]: ...
    def grant_permission(
        self, dataset_id: int, user_id: int, level: str,
        granted_by: int, expires_at: datetime | None = None
    ) -> DatasetPermissionRow: ...
    def revoke_permission(self, dataset_id: int, user_id: int) -> bool: ...
    def update_permission_level(self, dataset_id: int, user_id: int, level: str) -> DatasetPermissionRow | None: ...
    def check_permission(
        self, dataset_id: int, user_id: int,
        required_levels: list[str]
    ) -> bool: ...
```

### 3.4 Dependencies 变更 (`api/dependencies.py`)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dreamdata.auth.repository import AuthRepository, UserRow

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: str | None = Header(None),
    auth_repo: AuthRepository = Depends(get_auth_repository),
) -> UserRow:
    """
    支持两种认证方式：
    1. Bearer Token (JWT)
    2. X-API-Key Header
    """
    ...

async def require_admin(
    current_user: UserRow = Depends(get_current_user),
) -> UserRow:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return current_user

async def require_dataset_permission(
    dataset_name: str,
    required_levels: list[str] = ["owner", "read_write", "read_only"],
    current_user: UserRow = Depends(get_current_user),
    meta_repo: MetaRepository = Depends(get_meta_repository),
    auth_repo: AuthRepository = Depends(get_auth_repository),
) -> tuple[DatasetMeta, DatasetVersionMeta, str]:
    """
    检查用户对数据集的权限。
    Admin 自动拥有所有权限。
    Owner 拥有所有权限。
    """
    ds, v = meta_repo.get_dataset_by_name(name=dataset_name)

    if current_user.role == "admin":
        return ds, v, "admin"

    perm = auth_repo.get_dataset_permission(ds.id, current_user.id)
    if not perm:
        raise HTTPException(status_code=403, detail="No permission")

    if perm.permission_level not in required_levels:
        raise HTTPException(status_code=403, detail="Insufficient permission")

    return ds, v, perm.permission_level
```

### 3.5 现有路由更新

所有现有路由需要更新以使用新的依赖注入：

```python
# 示例：datasets.py
@router.get("/{name}", response_model=DatasetInfo)
async def get_dataset(
    name: str,
    auth_info: tuple[DatasetMeta, DatasetVersionMeta, str] = Depends(
        lambda: require_dataset_permission(name, ["read_only", "read_write", "owner"])
    ),
) -> DatasetInfo:
    ds, v, level = auth_info
    ...
```

---

## 4. 实现步骤

### Phase 1: 数据库层 (Step 1-2)

**Step 1**: 创建 Alembic 迁移
- 定义 `users`, `api_keys`, `dataset_permissions`, `password_reset_tokens` 表
- 添加索引和约束
- 编写 downgrade 逻辑

**Step 2**: 实现 AuthRepository
- 用户 CRUD 操作
- 权限 CRUD 操作
- 集成到现有 MetaConnection

### Phase 2: 认证核心 (Step 3-4)

**Step 3**: 实现密码哈希和令牌生成
- Argon2id 密码哈希
- JWT token 生成和验证
- API key 生成和验证

**Step 4**: 实现认证依赖注入
- `get_current_user` 支持 JWT 和 API key
- `require_admin` 检查
- `require_dataset_permission` 检查

### Phase 3: API 路由 (Step 5-7)

**Step 5**: 实现认证路由 (`/auth`)
- 初始设置 (`/setup`)
- 登录/登出
- 密码修改
- API key 管理

**Step 6**: 实现用户管理路由 (`/users`)
- 用户列表/创建/更新/删除
- 个人信息查看

**Step 7**: 实现权限管理路由 (`/permissions`)
- 权限分配/撤销
- 权限列表
- 用户权限查询

### Phase 4: 集成与更新 (Step 8-9)

**Step 8**: 更新现有路由
- 为所有数据集相关端点添加权限检查
- 更新错误响应
- 保持向后兼容（旧 API key 仍可工作，但映射到 "anonymous" 用户）

**Step 9**: 更新 Web UI
- 添加登录页面
- 添加用户管理页面（管理员）
- 添加权限管理页面
- 在 UI 中显示当前用户权限级别

### Phase 5: 测试与验证 (Step 10-12)

**Step 10**: 单元测试
- 密码哈希测试
- 权限检查测试
- Repository 层测试

**Step 11**: 集成测试
- API 端点测试
- 权限流程测试
- 向后兼容性测试

**Step 12**: 文档更新
- 更新 API 文档
- 添加用户指南
- 更新部署文档

---

## 5. 向后兼容性策略

### 5.1 API 兼容性

- **旧认证方式仍支持**: `X-API-Key` 和 `X-User-ID` header 继续工作
- **匿名用户映射**: 未认证请求映射到 "anonymous" 用户
- **Legacy 数据迁移**: 现有 `user_annotations` 中的 string user_id 继续保留
- **权限默认**: 现有数据集默认没有权限（除了 admin），需要管理员显式分配

### 5.2 迁移路径

1. 部署 v0.4.0
2. 访问 `/auth/setup` 创建初始管理员账号
3. 管理员为现有数据集分配权限
4. 邀请用户注册或由管理员创建账号

### 5.3 兼容层

```python
# 在 dependencies.py 中
async def get_legacy_user_id(
    x_user_id: str | None = Header(None),
    current_user: UserRow | None = Depends(get_current_user_safe),
) -> str:
    """
    兼容层：返回 legacy string user_id
    如果已认证，返回 str(user.id)；否则返回 x_user_id 或 "anonymous"
    """
    if current_user:
        return str(current_user.id)
    return x_user_id or "anonymous"
```

---

## 6. 权限级别定义

| 级别 | 描述 | 允许的操作 |
|------|------|-----------|
| `owner` | 数据集所有者 | 所有操作，包括删除、分配权限 |
| `read_write` | 读写权限 | 读取、修改、添加标签/注释、追加、变换 |
| `read_only` | 只读权限 | 读取、搜索、查看 |
| `admin` | 系统管理员 | 所有数据集的所有权限，用户管理 |

### 权限矩阵

| 操作 | owner | read_write | read_only | admin |
|------|-------|------------|-----------|-------|
| 查看数据集 | ✓ | ✓ | ✓ | ✓ |
| 搜索/扫描 | ✓ | ✓ | ✓ | ✓ |
| 添加标签/注释 | ✓ | ✓ | ✗ | ✓ |
| 追加数据 | ✓ | ✓ | ✗ | ✓ |
| 变换数据 | ✓ | ✓ | ✗ | ✓ |
| 重命名数据集 | ✓ | ✗ | ✗ | ✓ |
| 删除数据集 | ✓ | ✗ | ✗ | ✓ |
| 分配权限 | ✓ | ✗ | ✗ | ✓ |
| 管理用户 | ✗ | ✗ | ✗ | ✓ |

---

## 7. 安全考虑

### 7.1 密码安全
- Argon2id 哈希算法
- Salt 每个用户唯一
- 密码最小长度 8 字符
- 建议包含大小写、数字、特殊字符（但不强制）

### 7.2 Token 安全
- JWT 短期有效（15-30分钟）
- Refresh Token 长期有效（7天）
- API key 可撤销
- Token 存储在 HTTP-only cookie（Web UI）

### 7.3 速率限制
- 登录尝试：5 次/分钟
- API 请求：根据用户级别限制
- 密码重置：1 次/10分钟

### 7.4 审计
- 记录所有权限变更
- 记录登录失败/成功
- 记录敏感操作

---

## 8. Web UI 更新

### 8.1 新增页面

1. **登录页** (`/login`)
   - 用户名/密码输入
   - "记住我" 选项
   - 忘记密码链接

2. **用户管理** (`/admin/users`) - 管理员
   - 用户列表
   - 创建用户表单
   - 用户编辑/删除

3. **权限管理** (`/datasets/:name/permissions`)
   - 权限列表
   - 添加用户权限
   - 编辑/删除权限

4. **个人设置** (`/settings`)
   - 修改密码
   - API key 管理
   - 个人信息编辑

### 8.2 UI 组件更新

- 顶部导航栏显示当前用户和登出按钮
- 数据集列表显示用户对该数据集的权限级别
- 权限级别可视化（徽章/图标）

---

## 9. 测试计划

### 9.1 测试层次

| 层次 | 测试内容 |
|------|---------|
| L1 | 密码哈希、令牌生成、权限检查逻辑 |
| L2 | AuthRepository 单元测试 |
| L3 | API 端点集成测试、权限流程测试 |
| L4 | 权限矩阵验证测试 |
| L5 | 安全测试（SQL 注入、权限提升） |
| L6 | 并发权限变更测试 |
| L7 | 突变测试（认证逻辑） |
| L8 | E2E 测试（登录 → 创建数据集 → 分配权限 → 验证） |

### 9.2 关键测试场景

1. 初始管理员设置流程
2. 用户创建和权限分配
3. 权限不足时的 403 响应
4. 管理员绕过权限检查
5. 密码修改流程
6. API key 认证流程
7. 向后兼容性（旧 API key 仍工作）

---

## 10. 部署注意事项

### 10.1 环境变量

新增环境变量：

```bash
# JWT 密钥（必需）
JWT_SECRET_KEY=your-secret-key-here

# JWT 配置（可选）
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Argon2 配置（可选）
ARGON2_TIME_COST=3
ARGON2_MEMORY_COST=65536
ARGON2_PARALLELISM=4
```

### 10.2 迁移步骤

1. 备份数据库
2. 运行 Alembic 迁移：`uv run alembic upgrade head`
3. 重启服务
4. 访问 `/auth/setup` 创建初始管理员账号

---

## 11. 后续优化（v0.4.1+）

- OAuth2/SSO 集成
- 审计日志 UI
- 权限模板/角色
- 临时权限（过期时间）
- 操作通知
- 更细粒度的权限（例如：仅标签权限、仅导出权限）

---

## 总结

本计划覆盖了 v0.4.0 的完整实现，包括：
- 数据库 schema 设计与迁移
- API 端点设计
- 认证与权限系统实现
- 向后兼容性策略
- 安全考虑
- Web UI 更新
- 测试计划
- 部署指南
