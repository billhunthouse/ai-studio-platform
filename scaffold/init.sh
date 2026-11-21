#!/usr/bin/env bash
# 前端工程化脚手架初始化脚本
# 用法: bash init.sh /path/to/target-project
set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
  echo "用法: bash init.sh /path/to/target-project"
  echo "错误: 目标目录不存在或未指定"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$TARGET")"

echo "==> 初始化前端工程化脚手架"
echo "    目标项目: $PROJECT_NAME"
echo "    目标路径: $TARGET"

# 创建目录结构
mkdir -p "$TARGET/design/baseline/screens"
mkdir -p "$TARGET/design/after"

# 复制模板
cp "$SCRIPT_DIR/templates/DESIGN.template.md" "$TARGET/design/DESIGN.md"
cp "$SCRIPT_DIR/templates/tokens.template.json" "$TARGET/design/tokens.json"
cp "$SCRIPT_DIR/templates/component-inventory.template.md" "$TARGET/design/component-inventory.md"
cp "$SCRIPT_DIR/prompts/figma-ai-prompts.md" "$TARGET/design/figma-ai-prompts.md"
cp "$SCRIPT_DIR/scripts/verify.sh" "$TARGET/design/verify.sh"
chmod +x "$TARGET/design/verify.sh" 2>/dev/null || true

# 替换项目名占位符（跨平台 sed）
if command -v sed >/dev/null 2>&1; then
  sed -i.bak "s/PROJECT_NAME_PLACEHOLDER/$PROJECT_NAME/g" "$TARGET/design/DESIGN.md" 2>/dev/null || true
  rm -f "$TARGET/design/DESIGN.md.bak" 2>/dev/null || true
fi

# 生成使用说明
cat > "$TARGET/design/README.md" <<EOF
# $PROJECT_NAME — 设计基线包

本目录由前端工程化脚手架初始化生成。

## 下一步（按顺序）
1. 编辑 \`DESIGN.md\` 的 YAML frontmatter：改颜色、字体、项目名为本项目实际值
2. 编辑 \`tokens.json\`，与 DESIGN.md 保持一致（这是 Token 真相源）
3. 捕获当前 UI 截图，放入 \`baseline/screens/\`（1440×900）
4. 填 \`component-inventory.md\`：列出本项目核心组件
5. 用 \`figma-ai-prompts.md\` 推进 Figma AI 设计
6. 每个里程碑跑 \`bash verify.sh\` 验证

## 治理原则
- Token 以代码为准，视觉以 Figma 批准帧为准
- Token 变更走 PR，不在 Figma 建孤岛变量
- 先收敛 5 个高频组件，再批量做页面
EOF

echo ""
echo "==> 完成。已创建:"
echo "    design/DESIGN.md"
echo "    design/tokens.json"
echo "    design/component-inventory.md"
echo "    design/figma-ai-prompts.md"
echo "    design/verify.sh"
echo "    design/README.md"
echo ""
echo "下一步: 编辑 design/DESIGN.md 和 design/tokens.json 填入本项目实际值"
