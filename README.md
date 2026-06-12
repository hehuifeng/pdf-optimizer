# PDF Optimizer

压缩 Adobe Illustrator 导出的 PDF 文件，同时保持 Adobe Acrobat 兼容性。

## 原理

AI 导出的 PDF 文件中，每个导入对象被包装成独立的 Form XObject，每个 XObject 包含冗余的 Group、ExtGState、BBox、Matrix 等字典条目。此外还包含大量 AI 私有数据（PieceInfo）。

本脚本通过以下方式压缩：

1. **删除 AI 私有数据**：移除 `/PieceInfo` 和 `/Thumb`
2. **形状去重**：分析所有 XObject 流，发现其中只有少量不同的绘制形状，唯一差异是位置坐标
3. **模板 Form XObject**：为每种独特形状创建一个模板，放入页面级 Resources/XObject
4. **极简 wrapper**：每个原始 XObject 的流缩减为对模板的 Do 调用，删除其 `/Resources` 和 `/Group`，通过页面级资源继承获取 GS0 和模板引用
5. **位置移至 Matrix**：将每个 XObject 流内的位置坐标提取到 `/Matrix` 中，BBox 调整为本地坐标

## 使用方法

### 环境准备

```bash
conda create -n pdf-opt python=3.12 -y
conda activate pdf-opt
pip install pikepdf
```

### 运行

```bash
python optimize_final.py <input.ai|input.pdf>
```

输出文件名为 `<原名>_optimized.pdf`，保存在同目录下。

### 示例

```
$ python optimize_final.py illustration.ai
16.8 MB -> 3.7 MB (78% reduction)
Saved: illustration_optimized.pdf
```

## 验证

优化后的文件必须通过 Adobe Acrobat 验证。Ghostscript 可用于快速预检：

```bash
gs -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -sOutputFile=/dev/null output.pdf
```

**注意**：Ghostscript 通过不代表 Acrobat 通过。Mac Preview 过于宽松，不能替代 Acrobat。

## 适用条件

本脚本适用于满足以下条件的 PDF 文件：

- 由 Adobe Illustrator 导出
- 页面 Content Stream 中的 XObject（Form XObject）流结构为：`<图形状态设置> q 1 0 0 1 X Y cm <绘制指令> Q`
- 不同 XObject 之间存在大量重复的绘制形状（仅位置不同）

不满足上述结构的文件需要修改脚本中的正则匹配逻辑。

## 经验总结

### 红线

**不要修改页面 Content Stream 的任何字节。** 任何修改都会导致 Acrobat 报错"本页面上存在错误"，即使 Ghostscript 验证通过、Mac Preview 正常显示。

### 安全操作

| 操作 | 说明 |
|------|------|
| 删除 `/PieceInfo` | 去除 AI 私有数据 |
| 删除 `/Thumb` | 去除嵌入缩略图 |
| 删除 XObject 的 `/Resources` | XObject 可继承页面 Resources |
| 删除 XObject 的 `/Group` | 不透明内容不需要透明度组 |
| 修改 XObject 流内容 | 可以改写绘制指令或替换为 Do 调用 |
| 在页面 Resources 中添加模板 XObject | 供 XObject 流通过继承引用 |
| 修改 XObject 字典中的 GS0 引用 | 在原 dict 上修改值，不替换整个 dict |

### 不安全操作

| 操作 | 后果 |
|------|------|
| 修改页面 Content Stream | Acrobat 报错 |
| 替换 XObject 的整个 Resources 字典 | `xobj['/Resources'] = new_dict` 会导致 Acrobat 报错 |
| 向 XObject 的 Resources 添加 `/XObject` 条目 | Acrobat 报错 |
| XObject 保留自身 Resources 时让流调用模板 | 找不到模板，内容消失 |

核心规则：**对 XObject 的 Resources 只能删除或在原字典上修改值，不能替换整个字典或添加新条目。**

### 陷阱备忘

- `None` 是 Python 关键字，pikepdf 中必须用 `pikepdf.Name('/None')`
- `pikepdf.Dictionary({...})` 的 key 必须用字符串如 `'/GS0'`，不能用 `pikepdf.Name` 对象
- Content stream 中插入操作符必须确保前后有空白，否则产生无效 token
- `compress_streams=True` 会覆盖手动设置的 `/Filter`
