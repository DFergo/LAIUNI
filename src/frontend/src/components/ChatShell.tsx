import { useState, useRef, useEffect } from 'react'
import { t } from '../i18n'
import type { LangCode, SurveyData } from '../types'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  lang: LangCode
  sessionToken: string
  survey: SurveyData
}

export default function ChatShell({ lang, sessionToken, survey }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [queuePosition, setQueuePosition] = useState<number | null>(null)
  const [error, setError] = useState('')
  const chatEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isFirstMessage = useRef(true)
  const hasSentInitial = useRef(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  // Auto-send survey situation as first message on mount
  useEffect(() => {
    if (hasSentInitial.current) return
    hasSentInitial.current = true
    const situation = survey.description || ''
    if (situation) {
      submitMessage(situation)
    }
  }, [])

  const submitMessage = async (text: string) => {
    setError('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setIsStreaming(true)
    setStreamingText('')
    setQueuePosition(null)

    const messageId = crypto.randomUUID()
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

  const listenForResponse = () => {
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
      setQueuePosition(null)
    })

    eventSource.addEventListener('queue_position', (e: MessageEvent) => {
      connectionFailures = 0
      setQueuePosition(parseInt(e.data, 10))
    })

    eventSource.addEventListener('done', (e: MessageEvent) => {
      eventSource.close()
      setMessages(prev => [...prev, { role: 'assistant', content: e.data }])
      setStreamingText('')
      setIsStreaming(false)
      setQueuePosition(null)
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="max-w-4xl mx-auto flex flex-col h-[calc(100vh-64px)]">
      {/* Session token */}
      <div className="text-center text-xs text-gray-400 py-2 font-mono">{sessionToken}</div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 space-y-4 pb-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-lg px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-uni-blue text-white'
                  : 'bg-white border border-gray-200 text-gray-800'
              }`}
            >
              <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
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
                <div className="text-sm whitespace-pre-wrap">{streamingText}</div>
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

      {/* Input */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        <div className="flex gap-3 items-end max-w-4xl mx-auto">
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
        </div>
      </div>
    </div>
  )
}
