<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  api,
  type DemoAnalysis,
  type DemoMaterial,
  type RuntimeState,
} from '@/api/client'

const runtime = ref<RuntimeState | null>(null)
const key = ref(sessionStorage.getItem('engineering-key') || '')
const materials = ref<DemoMaterial[]>([])
const result = ref<DemoAnalysis | null>(null)
const error = ref('')
const busy = ref(false)
const uploadName = ref('')
const uploadPreview = ref('')
const uploadCase = ref<DemoMaterial['case_id']>('corridor_clutter')

const canRun = computed(() => ['COMMISSIONING', 'MAINTENANCE'].includes(runtime.value?.mode || ''))

function friendlyError(reason: unknown) {
  const text = reason instanceof Error ? reason.message : String(reason)
  if (text.includes('401')) return '工程密钥不正确，请检查 .env。'
  if (text.includes('409')) return '请先进入联调模式，再运行素材。'
  return '操作没有完成，请确认后端服务和工程密钥。'
}

async function loadRuntime() {
  try {
    runtime.value = await api.runtime()
  } catch {
    error.value = '无法读取运行模式，请先启动后端服务。'
  }
}

async function unlock() {
  if (!key.value.trim()) {
    error.value = '请输入 .env 中的工程密钥。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    materials.value = await api.demoMaterials(key.value.trim())
    sessionStorage.setItem('engineering-key', key.value.trim())
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    busy.value = false
  }
}

async function enterTestMode() {
  busy.value = true
  error.value = ''
  try {
    const target = runtime.value?.mode === 'ACTIVE' ? 'MAINTENANCE' : 'COMMISSIONING'
    runtime.value = await api.transitionRuntime(key.value, target)
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    busy.value = false
  }
}

async function runMaterial(material: DemoMaterial) {
  busy.value = true
  result.value = null
  error.value = ''
  try {
    result.value = await api.runDemoAnalysis(key.value, { case_id: material.case_id })
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    busy.value = false
  }
}

async function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    error.value = '只能选择图片素材。'
    return
  }
  if (file.size > 1_500_000) {
    error.value = '演示图片不能超过1.5MB，请先压缩。'
    return
  }
  uploadName.value = file.name
  uploadPreview.value = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('File read failed'))
    reader.readAsDataURL(file)
  })
}

async function runUpload() {
  if (!uploadPreview.value) {
    error.value = '请先选择一张本地图片。'
    return
  }
  busy.value = true
  result.value = null
  error.value = ''
  try {
    result.value = await api.runDemoAnalysis(key.value, {
      case_id: uploadCase.value,
      file_name: uploadName.value,
      preview_data_url: uploadPreview.value,
    })
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await loadRuntime()
  if (key.value) await unlock()
})
</script>

<template>
  <section class="engineering-console">
    <div class="console-heading">
      <div>
        <p class="eyebrow">仅限本机工程人员</p>
        <h1>让一份素材走完整个Agent链路</h1>
        <p class="lead">选择固定回放样本，或上传并人工标注一张测试图片。每一步都保留来源，不把规则演示冒充模型识别。</p>
      </div>
      <div class="runtime-chip"><span>当前模式</span><strong>{{ runtime?.mode || '读取中' }}</strong></div>
    </div>

    <div v-if="error" class="console-error" role="alert">{{ error }}</div>

    <section class="console-module access-module" aria-labelledby="access-title">
      <div class="module-number">01</div>
      <div class="module-body">
        <h2 id="access-title">连接本机工程接口</h2>
        <p>密钥只保存在当前浏览器标签页，不写入前端代码或日志。</p>
        <div class="key-row">
          <label>工程密钥<input v-model="key" type="password" autocomplete="off" placeholder="EHAGENT_ENGINEERING_API_KEY" /></label>
          <button type="button" :disabled="busy" @click="unlock">{{ materials.length ? '已连接' : '连接测试台' }}</button>
          <button v-if="materials.length && !canRun" class="secondary-button" type="button" :disabled="busy" @click="enterTestMode">
            进入联调模式
          </button>
        </div>
      </div>
    </section>

    <section class="console-module" :class="{ disabled: !materials.length }" aria-labelledby="material-title">
      <div class="module-number">02</div>
      <div class="module-body">
        <h2 id="material-title">选择测试素材</h2>
        <p>三组素材分别验证风险任务、整改复查和画质拒判。</p>
        <div class="material-grid">
          <article v-for="material in materials" :key="material.case_id" class="material-card">
            <img :src="material.thumbnail_url" :alt="material.name" />
            <div>
              <span class="source-tag">REPLAY · 固定结果</span>
              <h3>{{ material.name }}</h3>
              <p>{{ material.description }}</p>
              <small>预期：{{ material.expected_outcome }}</small>
              <button type="button" :disabled="busy || !canRun" @click="runMaterial(material)">
                {{ busy ? 'Agent运行中…' : '用这份素材测试' }}
              </button>
            </div>
          </article>
        </div>

        <details class="upload-panel">
          <summary>或者：上传自己的测试图片</summary>
          <div class="upload-content">
            <div class="upload-preview">
              <img v-if="uploadPreview" :src="uploadPreview" alt="本地上传素材预览" />
              <span v-else>本地图片预览</span>
            </div>
            <div class="upload-fields">
              <label>选择图片<input type="file" accept="image/*" @change="chooseFile" /></label>
              <label>人工指定预期案例
                <select v-model="uploadCase">
                  <option value="corridor_clutter">走廊障碍</option>
                  <option value="corridor_clear">通道已清理</option>
                  <option value="quality_insufficient">画质不足</option>
                </select>
              </label>
              <p class="honesty-note">上传图片尚未经过视觉模型；案例由工程人员人工指定，结果永久标记为MANUAL。</p>
              <button type="button" :disabled="busy || !canRun || !uploadPreview" @click="runUpload">运行人工标注素材</button>
            </div>
          </div>
        </details>
      </div>
    </section>

    <section class="console-module result-module" :class="{ disabled: !result }" aria-labelledby="result-title">
      <div class="module-number">03</div>
      <div class="module-body">
        <h2 id="result-title">查看Agent如何得出结果</h2>
        <template v-if="result">
          <div class="analysis-summary">
            <span :class="['outcome-badge', result.outcome.toLowerCase()]">{{ result.outcome }}</span>
            <strong>{{ result.summary }}</strong>
            <span>来源：{{ result.source_type }}</span>
          </div>
          <ol class="agent-timeline">
            <li v-for="stage in result.stages" :key="stage.key" :class="stage.status">
              <span class="stage-dot">{{ stage.status === 'complete' ? '✓' : '!' }}</span>
              <div><strong>{{ stage.label }}</strong><p>{{ stage.detail }}</p></div>
            </li>
          </ol>
          <div v-if="result.task" class="result-task-link">
            <div><span>任务 {{ result.task.task_id.slice(0, 8) }}</span><strong>{{ result.task.title }}</strong></div>
            <a href="/" target="_blank">到住户端处理这项任务 ↗</a>
          </div>
        </template>
        <p v-else class="module-placeholder">运行一份素材后，这里会展示观察、画质检查、规则判断和行动结果。</p>
      </div>
    </section>
  </section>
</template>
