# 土豆 Mod 管理器

用于管理 Left 4 Dead 2 `addons` 目录中的 VPK Mod，支持分类识别、启用/停用、冲突提示、角色调整、语音替换和喷漆管理。

## 开发运行

需要 Windows、Python 3.10 或更高版本，以及 Pillow：

```powershell
python -m pip install Pillow
python desktop_app.py
```

首次启动后，在左侧选择 L4D2 的 `left4dead2\addons` 目录。

## 便携版

便携版不需要安装 Python，直接运行发布目录中的 `土豆管理器.exe`，首次启动后选择自己的 Mod 目录。

## 注意

程序会修改用户选择的 Mod 目录中的文件。删除操作使用 Windows 回收站；启用/停用会通过 VPK 文件名后缀切换状态。
