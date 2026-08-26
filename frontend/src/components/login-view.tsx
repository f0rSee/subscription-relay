import { useState, type FormEvent } from "react"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import {
  Frame,
  FrameDescription,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from "@/components/reui/frame"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { KeyRoundIcon, RadioTowerIcon, TriangleAlertIcon } from "lucide-react"

interface LoginViewProps {
  adminConfigured: boolean
  onLogin: (username: string, password: string) => Promise<void>
}

export function LoginView({ adminConfigured, onLogin }: LoginViewProps) {
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setSubmitting(true)
    try {
      await onLogin(username, password)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось войти")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="grid min-h-svh place-items-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3 px-1">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <RadioTowerIcon className="size-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Subscription Relay</h1>
            <p className="text-sm text-muted-foreground">Панель управления подписками</p>
          </div>
        </div>

        <Frame spacing="lg">
          <FrameHeader>
            <FrameTitle className="text-base">Вход администратора</FrameTitle>
            <FrameDescription>
              Управляйте источниками и порядком серверов без перезапуска сервиса.
            </FrameDescription>
          </FrameHeader>
          <FramePanel>
            {!adminConfigured ? (
              <Alert variant="warning">
                <TriangleAlertIcon aria-hidden="true" />
                <AlertTitle>Вход ещё не настроен</AlertTitle>
                <AlertDescription>
                  Добавьте ADMIN_PASSWORD в окружение сервиса и перезапустите его один раз.
                </AlertDescription>
              </Alert>
            ) : (
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-1.5">
                  <Label htmlFor="username">Пользователь</Label>
                  <Input
                    id="username"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="password">Пароль</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </div>
                {error && (
                  <Alert variant="destructive">
                    <TriangleAlertIcon aria-hidden="true" />
                    <AlertTitle>Вход не выполнен</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
                <Button className="w-full" type="submit" disabled={submitting}>
                  <KeyRoundIcon aria-hidden="true" />
                  {submitting ? "Проверяю…" : "Войти"}
                </Button>
              </form>
            )}
          </FramePanel>
        </Frame>
      </div>
    </main>
  )
}
