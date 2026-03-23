# EpubReader 简易阅读器

一个基于 PyQt 的轻量级电子书阅读器，支持 TXT 与 EPUB，提供按行对齐的翻页体验、透明背景（仅文字）模式、置顶与防截屏等实用功能。

## 下载
[📥 点击下载最新版 (v1.0) - 无需安装，解压即用](https://github.com/hou720616/EpubReader/releases/tag/v1.0)

## 功能特性
- 支持加载 `.txt` 与 `.epub` 文件
- 自动分章：对超长文本按每 5 万字符切片以降低卡顿
- 章节跳转：从右键菜单快速选择章节
- 翻页与滚动：
  - 按行对齐翻页，避免累积误差
  - 滚轮按行滚动（步长为 3 行）
  - 键盘：A/PageUp 上一页，D/PageDown 下一页
  - 鼠标：窗口左半区上一页，右半区下一页；窗口边缘拖动调整大小
- 样式控制：字体、字体颜色、字体透明度、背景色、背景透明度
- 置顶与防截屏：可切换窗口置顶、防屏幕捕获
- 无边框窗口与边缘尺寸调整
- 进度记忆：按文件路径记录章节索引与滚动位置（校验 mtime/size）
- 最近文件记忆：配置文件中保存上次打开路径

## 目录结构
- 应用入口：[app.py](file:///g:/PyProject/EpubReader/app.py)
- 主程序：[main.py](file:///g:/PyProject/EpubReader/main.py)
- UI 窗口与交互逻辑：[reader_window.py](file:///g:/PyProject/EpubReader/reader_window.py)
- Qt 兼容层（PyQt6/PyQt5）：[qt_compat.py](file:///g:/PyProject/EpubReader/qt_compat.py)
- EPUB 解析与文本读取：[epub_utils.py](file:///g:/PyProject/EpubReader/epub_utils.py)
- 配置文件（字体、颜色、上次文件等）：[reader_config.json](file:///g:/PyProject/EpubReader/reader_config.json)

## 环境要求
- Windows（已验证）
- Python 3.12+
- 依赖其一：PyQt6 或 PyQt5

安装依赖示例：
```bash
pip install PyQt6
# 或
pip install PyQt5
```

## 运行
在项目根目录：
```bash
python app.py
```
直接指定文件启动：
```bash
python main.py --file "D:\path\to\book.epub"
```

## 配置与进度
- 配置文件：`reader_config.json`
  - `last_path`：上次打开的文件路径。若该路径在目标机器不存在，程序会跳过加载并正常启动到空白界面。
  - 字体与颜色、透明度等参数会在菜单调整后写回配置。
- 阅读进度：`~/.epubrand_progress.json`
  - 按文件路径记录 `chapter` 与 `scroll`（滚动条位置），并校验 `mtime` 与 `size`，确保进度与当前文件匹配。

## 常用操作
- 右键菜单：打开文件、章节跳转、上一页/下一页、字体设置、字体颜色、字体透明度、背景色、背景透明度、置顶、防截屏、退出
- 键盘：A/PageUp 上一页；D/PageDown 下一页
- 鼠标：
  - 左半区单击上一页，右半区单击下一页
  - 边缘拖动进行无边框窗口的尺寸调整
  - 滚轮按行滚动

## 打包为 EXE
使用 PyInstaller（需已安装）：
```bash
pyinstaller --name "EpubReader" --onefile --windowed --icon ico/yu.ico app.py
```
发布建议：
- 将生成的 `dist/EpubReader.exe` 与一个 `reader_config.json` 放入 `Release/` 目录后分发
- 为提升初次体验，建议将 `reader_config.json` 中的 `last_path` 留空（不存在的路径会被正常忽略）

## 常见问题
- 未安装 PyQt6/PyQt5：请先安装其中之一
- `last_path` 指向不存在的文件：程序会跳过加载，不会崩溃
- 透明背景模式：
  - 当背景透明度设为 `0%` 时，仅显示文字；内部会切换窗口属性确保正常渲染与交互
