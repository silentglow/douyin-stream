# 贡献指南

感谢你对 Media Tools 项目的关注！我们欢迎所有形式的贡献。

---

## 🚀 快速开始

### 1. Fork 项目

在 GitHub 上点击 "Fork" 按钮，创建你自己的副本。

### 2. 克隆到本地

```bash
git clone https://github.com/YOUR_USERNAME/media-tools.git
cd media-tools
```

### 3. 设置开发环境

```bash
# 推荐：使用 uv（项目已包含 uv.lock）
uv sync

# 或 pip 安装（含开发依赖）
pip install -e ".[dev]"

# 或仅安装运行依赖
pip install -e .
```

### 4. 创建分支

```bash
git checkout -b feature/your-feature-name
```

---

## 📝 贡献方式

### 1. 报告 Bug

如果你发现了 Bug，请创建一个 Issue 并包含：

- **简短描述** Bug 是什么
- **复现步骤** 如何触发
- **预期行为** 应该发生什么
- **实际行为** 实际发生了什么
- **环境信息** Python版本、操作系统等

### 2. 提出新功能

如果你想添加新功能，请创建一个 Issue 并说明：

- **功能描述** 你想添加什么
- **使用场景** 为什么需要这个功能
- **实现思路** 你打算如何实现（可选）

### 3. 提交代码

#### 开发流程

1. **保持更新** 
   ```bash
   git remote add upstream https://github.com/ORIGINAL_OWNER/media-tools.git
   git fetch upstream
   git rebase upstream/main
   ```

2. **开发功能**
   - 编写代码
   - 添加测试
   - 更新文档

3. **运行测试**
   ```bash
   uv run pytest
   ```

4. **提交代码**
   ```bash
   git add -A
   git commit -m "feat: 添加XXX功能"
   git push origin feature/your-feature-name
   ```

5. **创建 Pull Request**
   - 在 GitHub 上创建 PR
   - 填写清晰的描述
   - 等待代码审查

#### 提交信息规范

我们使用 [约定式提交](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Type 类型：**
- `feat`: 新功能
- `fix`: Bug修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/辅助工具

**示例：**
```
feat(pipeline): 添加失败重试机制

- 支持最多3次重试
- 指数退避策略
- 添加相关测试

Closes #123
```

---

## 🧪 测试要求

### 运行测试

```bash
# 运行所有测试
pytest

# 运行指定测试文件
pytest tests/test_exceptions.py

# 带详细输出
pytest -v
```

### 代码检查

```bash
# Lint 检查
ruff check src/ tests/

# 格式化
ruff format src/ tests/

# 类型检查（可选）
mypy src/
```

### 添加测试

每个新功能都应该包含测试：

```python
def test_your_feature():
    # 准备
    ...
    
    # 执行
    result = your_function()
    
    # 断言
    assert result == expected
```

### 测试覆盖率

目标是保持 80%+ 的测试覆盖率。

---

## 📚 代码规范

### Python 风格

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)
- 使用 4 个空格缩进
- 最大行长度 88 字符
- 使用类型提示

### 文档字符串

```python
def your_function(param1: str, param2: int) -> bool:
    """简短描述功能
    
    详细描述（如果需要）。
    
    Args:
        param1: 参数1说明
        param2: 参数2说明
        
    Returns:
        返回值说明
        
    Raises:
        ExceptionType: 异常说明
    """
    pass
```

### 中文注释

- 注释使用中文
- 保持清晰简洁
- 解释"为什么"而非"是什么"

---

## 📖 文档更新

### 更新 README

如果添加了新功能，记得更新：

1. README_V2.md 中的功能列表
2. CHANGELOG.md 添加变更记录
3. 使用教程或示例

### 示例代码

为新功能提供示例：

```python
# 示例：使用新功能
from src.media_tools.your_module import YourClass

instance = YourClass()
result = instance.do_something()
print(result)
```

---

## 🔍 代码审查

所有 PR 都需要经过代码审查。审查者会检查：

- ✅ 功能是否按描述工作
- ✅ 测试是否充分
- ✅ 代码规范是否遵循
- ✅ 文档是否更新
- ✅ 是否有性能问题
- ✅ 是否有安全隐患

---

## 🎯 贡献领域

我们特别欢迎以下方向的贡献：

### 核心功能
- [ ] 支持更多视频平台（B站、快手等）
- [ ] 支持更多AI转写服务（讯飞、OpenAI等）
- [ ] 插件化架构实现
- [ ] Web控制面板

### 用户体验
- [ ] 更友好的错误提示
- [ ] 更多配置预设
- [ ] 使用教程完善
- [ ] 视频演示

### 技术优化
- [ ] 提升测试覆盖率
- [ ] 性能优化
- [ ] 代码重构
- [ ] 依赖升级

### DevOps
- [ ] Docker Compose配置
- [ ] 更多CI/CD检查
- [ ] 自动化发布
- [ ] 性能监控

---

## 🙏 致谢

所有贡献者都会被记录在 [CONTRIBUTORS](CONTRIBUTORS) 文件中。

感谢每一位帮助改进这个项目的人！

---

## 📄 开源协议

本项目采用 MIT 协议。提交代码即表示你同意将代码以 MIT 协议发布。

---

## ❓ 有问题？

- 查看 [FAQ](references/FAQ.md)
- 创建 [Issue](https://github.com/YOUR_REPO/media-tools/issues)
- 参与 [Discussions](https://github.com/YOUR_REPO/media-tools/discussions)

---

**再次感谢你的贡献！🎉**
