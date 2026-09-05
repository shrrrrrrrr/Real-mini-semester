/**
 * 我的页：个人资料（头像上传+压缩、昵称）+ AI 服务设置（优先于 .env）+ 学习统计。
 *
 * 头像压缩：Canvas 缩放至 96×96 + JPEG quality 0.8（约 10-20KB），
 * 前端压缩后 base64 存储——本地应用不上传服务器。
 */

import { useEffect, useRef, useState } from 'react'
import { api, errText } from '../lib/api'
import type { Course, Profile, Stats } from '../lib/types'
import { useToast } from '../components/Toast'

/** Canvas 压缩图片为 96×96 JPEG base64。 */
function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      const canvas = document.createElement('canvas')
      canvas.width = 96
      canvas.height = 96
      const ctx = canvas.getContext('2d')
      if (!ctx) return reject(new Error('Canvas 不可用'))
      // 居中裁剪成正方形再缩放
      const side = Math.min(img.width, img.height)
      ctx.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, 96, 96)
      resolve(canvas.toDataURL('image/jpeg', 0.8))
    }
    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = url
  })
}

export function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [nickname, setNickname] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [testing, setTesting] = useState(false)
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [stats, setStats] = useState<Stats | null>(null)
  const avatarRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    void (async () => {
      try {
        const p = await api.get<Profile>('/profile')
        setProfile(p)
        setNickname(p.nickname)
        setBaseUrl(p.llm_base_url ?? '')
        setModel(p.llm_model ?? '')
      } catch (e) {
        toast(errText(e), 'error')
      }
    })()
  }, [toast])

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.get<Course[]>('/courses')
        setCourses(list)
        if (list.length > 0) setCourseId(list[0].id)
      } catch {
        /* 无课程时统计区为空 */
      }
    })()
  }, [])

  useEffect(() => {
    if (!courseId) return
    void (async () => {
      try {
        setStats(await api.get<Stats>(`/courses/${courseId}/stats`))
      } catch {
        /* ignore */
      }
    })()
  }, [courseId])

  async function saveProfile(patch: Record<string, unknown>) {
    try {
      const p = await api.patch<Profile>('/profile', patch)
      setProfile(p)
      return p
    } catch (e) {
      toast(errText(e), 'error')
      return null
    }
  }

  async function pickAvatar(file: File) {
    try {
      const base64 = await compressImage(file)
      const p = await saveProfile({ avatar: base64 })
      if (p) toast('头像已更新')
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function testConnection() {
    setTesting(true)
    try {
      // 先保存当前输入（可能还没保存）
      await saveProfile({
        llm_base_url: baseUrl,
        llm_model: model,
        ...(apiKey ? { llm_api_key: apiKey } : {}),
      })
      setApiKey('') // 输入框清空（已保存）
      const r = await api.post<{ ok: boolean; model: string }>('/profile/llm-test')
      toast(`连接成功（模型：${r.model}）`)
    } catch (e) {
      toast(errText(e), 'error')
    } finally {
      setTesting(false)
    }
  }

  const level = (reviewed: number): number => {
    if (reviewed === 0) return 0
    if (reviewed < 10) return 1
    if (reviewed < 25) return 2
    if (reviewed < 50) return 3
    return 4
  }

  return (
    <>
      <div className="section-label reveal">
        <span>ME.ZONE</span>
        <p>我的</p>
        <i></i>
      </div>

      {/* ---- 个人资料 ---- */}
      <div className="panel reveal delay-1" style={{ padding: '22px', display: 'flex', gap: '22px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '18px' }}>
        <button
          className="brand-avatar"
          style={{ width: 84, height: 84, fontSize: 34, cursor: 'pointer', overflow: 'hidden', border: '4px solid var(--line)' }}
          onClick={() => avatarRef.current?.click()}
          title="点击更换头像"
          aria-label="更换头像"
        >
          {profile?.avatar ? (
            <img src={profile.avatar} alt="头像" style={{ width: '100%', height: '100%', objectFit: 'cover', imageRendering: 'pixelated' }} />
          ) : (
            (profile?.nickname ?? '学')[0]
          )}
        </button>
        <input
          ref={avatarRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => e.target.files?.[0] && void pickAvatar(e.target.files[0])}
        />
        <div style={{ flex: 1, minWidth: 220 }}>
          <b style={{ font: '700 22px/1 var(--pixel)', color: 'var(--ink-strong)' }}>{profile?.nickname ?? '…'}</b>
          <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
            <input
              className="pixel-input"
              placeholder="修改昵称"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              style={{ flex: 1, minHeight: 38 }}
            />
            <button className="btn btn-primary" onClick={() => void saveProfile({ nickname }).then((p) => p && toast('昵称已保存'))}>
              保存
            </button>
          </div>
          <p style={{ margin: '8px 0 0', color: 'var(--muted)', fontSize: 12 }}>
            点击头像更换图片（自动压缩为 96×96）
          </p>
        </div>
      </div>

      {/* ---- AI 服务设置 ---- */}
      <div className="panel reveal delay-2" style={{ padding: '22px', marginBottom: '18px' }}>
        <b style={{ font: '700 7px/1 var(--mono)', color: 'var(--ink-strong)' }}>AI 服务设置</b>
        <p style={{ color: 'var(--muted)', fontSize: 12, margin: '6px 0 14px' }}>
          此处配置优先于 backend/.env；Key 明文存本机数据库（单机应用，数据不出本机），界面脱敏显示
          {profile?.llm_key_hint && `（当前：${profile.llm_key_hint}）`}
        </p>
        <div style={{ display: 'grid', gap: '10px' }}>
          <label style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span style={{ font: "7px/1 var(--mono)", width: 90 }}>接口地址</span>
            <input className="pixel-input" placeholder="https://api.deepseek.com/v1" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} style={{ flex: 1, minHeight: 38 }} />
          </label>
          <label style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span style={{ font: "7px/1 var(--mono)", width: 90 }}>模型名</span>
            <input className="pixel-input" placeholder="deepseek-chat" value={model} onChange={(e) => setModel(e.target.value)} style={{ flex: 1, minHeight: 38 }} />
          </label>
          <label style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span style={{ font: "7px/1 var(--mono)", width: 90 }}>API Key</span>
            <input className="pixel-input" placeholder={profile?.llm_key_hint ?? 'sk-…（留空则不修改）'} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ flex: 1, minHeight: 38 }} />
          </label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button className="btn btn-primary" onClick={() => void testConnection()} disabled={testing}>
              {testing ? '测试中…' : '保存并测试连接'}
            </button>
            {profile?.llm_key_hint && (
              <button className="btn btn-danger" onClick={() => void saveProfile({ llm_api_key: '__clear__' }).then((p) => p && toast('Key 已清除'))}>
                清除 Key
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ---- 学习统计 ---- */}
      <div className="panel reveal delay-3" style={{ padding: '22px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <b style={{ font: '700 7px/1 var(--mono)', color: 'var(--ink-strong)' }}>学习统计</b>
          {courses.length > 0 && (
            <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)} style={{ minHeight: 36 }}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}
        </div>

        {stats ? (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px', marginTop: '14px' }}>
              {[
                { label: '闪卡总数', value: stats.total_cards },
                { label: '今日到期', value: stats.due_today },
                { label: '今日已复习', value: stats.reviewed_today },
                { label: '正确率', value: `${(stats.correct_rate * 100).toFixed(0)}%` },
                { label: '连续学习', value: `${stats.streak_days} 天` },
              ].map((c) => (
                <div key={c.label} className="panel-soft" style={{ padding: '14px', textAlign: 'center' }}>
                  <div style={{ font: '700 26px/1 var(--pixel)', color: 'var(--ink-strong)' }}>{c.value}</div>
                  <div style={{ font: "7px/1 var(--mono)", color: 'var(--muted)', marginTop: 6 }}>{c.label}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: '16px' }}>
              <b style={{ font: "7px/1 var(--mono)" }}>近 7 天复习热力图</b>
              <div style={{ display: 'flex', gap: '10px', marginTop: '10px', alignItems: 'flex-end' }}>
                {stats.last_7_days.map((d) => (
                  <div key={d.date} style={{ textAlign: 'center' }}>
                    <div className="heatmap" style={{ gridTemplateRows: 'repeat(1, 28px)' }}>
                      <i data-level={level(d.reviewed)} style={{ width: 28, height: 28 }} title={`${d.date}：复习 ${d.reviewed} 张 / 到期 ${d.due} 张`} />
                    </div>
                    <small style={{ font: "7px/1 var(--mono)", color: 'var(--muted)' }}>{d.date.slice(5)}</small>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <p style={{ color: 'var(--muted)', margin: '14px 0 0' }}>
            {courses.length === 0 ? '先去资料库建课程，学起来之后这里就有数据了。' : '加载中…'}
          </p>
        )}
      </div>

      <p style={{ color: 'var(--muted)', font: "7px/1.6 var(--mono)", marginTop: '14px' }}>
        * 新手教程将在功能完善后上线；「重看教程」入口届时开放。
      </p>
    </>
  )
}
