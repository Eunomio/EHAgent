<template>
  <section class="admin-dashboard">
    <p class="eyebrow">产品与研究管理</p>
    <h1>产品模块与演示边界</h1>
    <p class="lead">这里明确展示当前已经可以验收的闭环，以及仍需真实设备和视觉模型才能完成的能力。</p>
    <div class="grid">
      <article class="panel"><span class="source-tag">已实现 · v0.2</span><h2>素材分析闭环</h2><p>Replay与人工标注素材可经过画质、规则、任务和反馈阶段。</p></article>
      <article class="panel"><span class="source-tag">已实现 · v0.2</span><h2>住户任务反馈</h2><p>提供已处理、稍后、不是风险和暂停四个固定动作，并保存审计记录。</p></article>
      <article class="panel"><span class="source-tag">已实现 · v0.2</span><h2>整改后复查</h2><p>“已处理”不会直接关闭；使用整改后素材复查通过才进入已解决。</p></article>
      <article class="panel"><span class="source-tag pending">尚未实现</span><h2>真实视觉识别</h2><p>当前上传素材必须人工指定案例，不能用于验证模型准确率。</p></article>
      <article class="panel"><span class="source-tag pending">尚未实现</span><h2>萤石设备输入</h2><p>摄像机接入、区域标定和真实采集仍等待平台PoC。</p></article>
      <article class="panel"><span class="source-tag pending">尚未实现</span><h2>正式报告</h2><p>正式指标必须隔离REAL_DEVICE、REPLAY与MANUAL数据后再生成。</p></article>
    </div>
    <p class="admin-entry"><a href="/engineering">进入工程测试台，运行一次完整演示 →</a></p>
  </section>
</template>
