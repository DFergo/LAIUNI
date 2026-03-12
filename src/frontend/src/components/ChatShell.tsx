import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { t } from '../i18n'
import type { LangCode, SurveyData, RecoveryData } from '../types'

interface Message {
  role: 'user' | 'assistant'
  content: string
  isSummary?: boolean
}

interface Props {
  lang: LangCode
  sessionToken: string
  survey: SurveyData
  recoveryData?: RecoveryData | null
}

export default function ChatShell({ lang, sessionToken, survey, recoveryData }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [queuePosition, setQueuePosition] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [sessionEnded, setSessionEnded] = useState(recoveryData?.status === 'completed')
  const [showEndConfirm, setShowEndConfirm] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isFirstMessage = useRef(!recoveryData)  // Not first if recovering
  const hasSentInitial = useRef(!!recoveryData)  // Don't auto-send on recovery
  const eventSourceRef = useRef<EventSource | null>(null)
  const userScrolledUp = useRef(false)

  // Auto-scroll only if user is at the bottom
  useEffect(() => {
    if (!userScrolledUp.current) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, streamingText])

  const handleScroll = () => {
    const el = scrollContainerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    userScrolledUp.current = !atBottom
  }

  // Auto-send survey situation as first message on mount (new sessions only)
  useEffect(() => {
    if (hasSentInitial.current) return
    hasSentInitial.current = true
    const situation = survey.description || ''
    if (situation) {
      submitMessage(situation)
    }
  }, [])

  const submitMessage = async (text: string) => {
    userScrolledUp.current = false
    setError('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setIsStreaming(true)
    setStreamingText('')
    setQueuePosition(null)

    // crypto.randomUUID() requires HTTPS — use fallback for plain HTTP
    const messageId = crypto.randomUUID?.()
      ?? `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
    const timestamp = new Date().toISOString()

    try {
      // Open SSE stream BEFORE posting — avoids race condition
      listenForResponse()

      // Submit message to sidecar queue
      const body: Record<string, unknown> = {
        session_token: sessionToken,
        content: text,
        message_id: messageId,
        timestamp,
        language: lang,
      }

      // Include survey data on first message
      if (isFirstMessage.current) {
        body.survey = survey
        isFirstMessage.current = false
      }

      await fetch('/internal/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch {
      setIsStreaming(false)
      setError('Failed to send message. Please try again.')
    }
  }

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    submitMessage(text)
  }

  const listenForResponse = (finalizing = false) => {
    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }
    const eventSource = new EventSource(`/internal/stream/${sessionToken}`)
    eventSourceRef.current = eventSource
    let connectionFailures = 0
    let accumulated = ''

    eventSource.addEventListener('token', (e: MessageEvent) => {
      connectionFailures = 0
      accumulated += e.data
      setStreamingText(accumulated)
      setIsStreaming(true)
      setQueuePosition(null)
    })

    eventSource.addEventListener('queue_position', (e: MessageEvent) => {
      connectionFailures = 0
      setQueuePosition(parseInt(e.data, 10))
    })

    eventSource.addEventListener('done', (e: MessageEvent) => {
      eventSource.close()
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: e.data,
        isSummary: finalizing,
      }])
      setStreamingText('')
      setIsStreaming(false)
      setQueuePosition(null)
      setUploadStatus(null)
      if (finalizing) {
        setSessionEnded(true)
      }
    })

    eventSource.addEventListener('upload_received', (e: MessageEvent) => {
      connectionFailures = 0
      setUploadStatus(`Processing ${e.data}...`)
    })

    eventSource.addEventListener('upload_processed', (e: MessageEvent) => {
      connectionFailures = 0
      try {
        const info = JSON.parse(e.data)
        if (info.type === 'image') {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `📎 **${info.filename}** — ${t('upload_image_stored', lang)}`,
          }])
          setUploadStatus(null)
        } else {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `📎 **${info.filename}** — ${t('upload_doc_analyzed', lang)}`,
          }])
          // Keep status visible until LLM response arrives (cleared on 'done')
          setUploadStatus(t('upload_analyzing', lang))
        }
      } catch {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `📎 ${t('upload_doc_analyzed', lang)}`,
        }])
        setUploadStatus(null)
      }
    })

    eventSource.addEventListener('upload_error', (e: MessageEvent) => {
      connectionFailures = 0
      setUploadStatus(null)
      setError(e.data || 'Upload processing failed')
    })

    eventSource.addEventListener('error', (e: MessageEvent) => {
      eventSource.close()
      setStreamingText('')
      setIsStreaming(false)
      setQueuePosition(null)
      setError(e.data || 'An error occurred')
    })

    // Lesson #1: unblock UI after 3 consecutive connection failures
    eventSource.onerror = () => {
      connectionFailures++
      if (connectionFailures >= 3) {
        eventSource.close()
        setStreamingText('')
        setIsStreaming(false)
        setQueuePosition(null)
        setError('Connection lost. Please try again.')
      }
    }
  }

  const endSession = async () => {
    setShowEndConfirm(false)

    setError('')
    setIsStreaming(true)
    setStreamingText('')
    setQueuePosition(null)

    const messageId = crypto.randomUUID?.()
      ?? `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
    const timestamp = new Date().toISOString()

    try {
      listenForResponse(true)

      await fetch('/internal/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_token: sessionToken,
          content: '',
          message_id: messageId,
          timestamp,
          language: lang,
          finalize: true,
        }),
      })
    } catch {
      setIsStreaming(false)
      setError('Failed to end session. Please try again.')
    }
  }

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    // Reset input so same file can be re-selected
    e.target.value = ''

    setUploadStatus(`Uploading ${file.name}...`)
    setError('')

    // Open SSE to receive upload events (if not already streaming)
    if (!eventSourceRef.current || eventSourceRef.current.readyState === EventSource.CLOSED) {
      listenForResponse()
    }

    const formData = new FormData()
    formData.append('file', file)

    try {
      const resp = await fetch(`/internal/upload/${sessionToken}`, {
        method: 'POST',
        body: formData,
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: 'Upload failed' }))
        throw new Error(body.detail || `HTTP ${resp.status}`)
      }
    } catch (err) {
      setUploadStatus(null)
      setError(err instanceof Error ? err.message : 'Upload failed')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Recovery: show previous session context
  const recoverySummary = recoveryData?.recovery_type === 'summary' ? recoveryData.summary : null
  const recoveryMessages = recoveryData?.recovery_type === 'full' ? recoveryData.messages : null

  return (
    <div className="max-w-4xl mx-auto flex flex-col h-[calc(100vh-64px)]">
      {/* Session token */}
      <div className="text-center text-xs text-gray-400 py-2 font-mono">{sessionToken}</div>

      {/* Messages */}
      <div ref={scrollContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 space-y-4 pb-4">

        {/* Recovery: previous session summary */}
        {recoverySummary && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl px-5 py-4 text-sm text-gray-700">
            <div className="text-xs font-semibold text-uni-blue mb-2 uppercase tracking-wide">
              Previous session summary ({recoveryData?.message_count} messages)
            </div>
            <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-800">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{recoverySummary}</ReactMarkdown>
            </div>
          </div>
        )}

        {/* Recovery: previous messages (short conversations) */}
        {recoveryMessages && recoveryMessages.length > 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-5 py-4 space-y-3">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Previous conversation
            </div>
            {recoveryMessages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm opacity-75 ${
                    msg.role === 'user'
                      ? 'bg-uni-blue/20 text-gray-700'
                      : 'bg-white border border-gray-200 text-gray-600'
                  }`}
                >
                  {msg.role === 'user' ? msg.content : (
                    <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-600 prose-li:text-gray-600 prose-strong:text-gray-700">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Separator after recovery context */}
        {recoveryData && (
          <div className="flex items-center gap-3 text-xs text-gray-400">
            <div className="flex-1 border-t border-gray-200" />
            <span>Session resumed</span>
            <div className="flex-1 border-t border-gray-200" />
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-lg px-4 py-3 ${
                msg.isSummary
                  ? 'bg-green-50 border-2 border-green-300 text-gray-800'
                  : msg.role === 'user'
                    ? 'bg-uni-blue text-white'
                    : 'bg-white border border-gray-200 text-gray-800'
              }`}
            >
              {msg.isSummary && (
                <div className="text-xs font-semibold text-green-700 mb-2 uppercase tracking-wide">
                  {t('session_summary_label', lang)}
                </div>
              )}
              {msg.role === 'user' ? (
                <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <div className="text-sm prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Streaming response */}
        {isStreaming && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg px-4 py-3 bg-white border border-gray-200 text-gray-800">
              {queuePosition !== null && !streamingText && (
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span className="inline-block w-2 h-2 bg-uni-blue rounded-full animate-pulse" />
                  {queuePosition === 1
                    ? 'Processing...'
                    : `Position ${queuePosition} in queue...`}
                </div>
              )}
              {!streamingText && queuePosition === null && (
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span className="inline-block w-2 h-2 bg-uni-blue rounded-full animate-pulse" />
                  Preparing...
                </div>
              )}
              {streamingText && (
                <div className="text-sm prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        )}

        {error && (
          <div className="text-center">
            <span className="text-sm text-uni-red">{error}</span>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Confirmation dialog */}
      {showEndConfirm && (
        <div className="border-t border-gray-200 bg-red-50 px-4 py-3">
          <div className="max-w-4xl mx-auto text-center space-y-3">
            <p className="text-sm text-gray-700">{t('end_session_confirm', lang)}</p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={endSession}
                className="bg-uni-red text-white rounded-lg px-5 py-2 text-sm font-medium transition-colors hover:opacity-90"
              >
                {t('end_session_yes', lang)}
              </button>
              <button
                onClick={() => setShowEndConfirm(false)}
                className="border border-gray-300 text-gray-700 rounded-lg px-5 py-2 text-sm font-medium transition-colors hover:bg-gray-50"
              >
                {t('end_session_no', lang)}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        {sessionEnded ? (
          <div className="text-center text-sm text-gray-500 py-2">
            {t('session_ended_notice', lang)}
          </div>
        ) : (
          <>
          <div className="flex gap-3 items-end max-w-4xl mx-auto">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,.doc,.docx,.jpg,.jpeg,.png"
              onChange={handleUpload}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming || !!uploadStatus}
              title={t('upload_button_title', lang)}
              className="text-gray-400 hover:text-uni-blue transition-colors disabled:opacity-50 disabled:cursor-not-allowed px-1 py-2.5"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </button>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('chat_placeholder', lang)}
              rows={2}
              disabled={isStreaming}
              className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none resize-none text-sm disabled:opacity-50"
            />
            <button
              onClick={sendMessage}
              disabled={isStreaming || !input.trim()}
              className="bg-uni-blue text-white rounded-lg px-5 py-2.5 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
            {!isStreaming && (
              <button
                onClick={() => setShowEndConfirm(true)}
                className="border border-uni-red text-uni-red rounded-lg px-4 py-2.5 text-sm font-medium transition-colors hover:bg-red-50"
              >
                {t('end_session', lang)}
              </button>
            )}
          </div>
          {uploadStatus && (
            <div className="max-w-4xl mx-auto mt-2">
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span className="inline-block w-2 h-2 bg-uni-blue rounded-full animate-pulse" />
                {uploadStatus}
              </div>
            </div>
          )}
          </>
        )}
      </div>
    </div>
  )
}
