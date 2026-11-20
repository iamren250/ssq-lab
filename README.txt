# 双色球实验室（独立静态版）

## 文件
- `index.html`：完整应用
- `manifest.json`、`icon.svg`：主屏幕安装信息和图标
- `sw.js`：离线缓存

## 部署
将这四个文件放在 GitHub 仓库根目录，在仓库 Settings → Pages 中选择 Deploy from a branch、`main`、`/(root)` 保存。等待部署完成后，用 Safari 打开 GitHub Pages 给出的 HTTPS 地址，再通过分享菜单添加到主屏幕。

## 数据说明
预测与开奖数据保存在当前浏览器 localStorage，不会自动同步到其他设备。请定期使用“数据备份”导出 JSON 文件。
