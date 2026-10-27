// 自绘标题栏：窗口隐藏了系统标题栏并使用 overlay 按钮，这里提供可拖动区域与品牌标语。
export default function TitleBar() {
  return (
    <div className="titlebar">
      {/* 除文字外整条留白都可拖动窗口，窗口按钮由系统绘制在右上角覆盖层 */}
      <span className="titlebar-slogan">本地运行 · 数据不出设备</span>
    </div>
  );
}
