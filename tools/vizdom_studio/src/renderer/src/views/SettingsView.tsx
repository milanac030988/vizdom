import clsx from 'clsx'
import { FileJson, FilePlus2, FolderOpen, RotateCcw, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { openConfig, saveConfigAs } from '../actions'
import { api } from '../api'
import { Badge, Button, Field, Input, Select, Switch } from '../components/ui'
import { useStudio } from '../store'
import type { Strategy } from '../types'

const DETECTORS = [
  { value: 'modular', label: 'modular: OmniParser boxes + OCR + roles (recommended)' },
  { value: 'omniparser', label: 'omniparser: icon detector + Florence captions' },
  { value: 'uied', label: 'uied: classic CV, no GPU needed' },
  { value: 'yolo', label: 'yolo: a trained YOLO model' },
  { value: 'hybrid', label: 'hybrid: UIED + YOLO' },
  { value: 'grpc', label: 'grpc: a running detector service' }
]
const OCR = [
  { value: 'easyocr', label: 'EasyOCR' },
  { value: 'paddleocr', label: 'PaddleOCR' },
  { value: 'tesseract', label: 'Tesseract' },
  { value: 'none', label: 'None (boxes only)' }
]
const TIERS = ['lexical', 'slm', 'vlm']

function get(cfg: Record<string, Record<string, unknown>> | undefined, path: string): unknown {
  const [a, b] = path.split('.')
  return cfg?.[a]?.[b]
}

export function SettingsView() {
  const config = useStudio((s) => s.config)
  const { setConfig, toast } = useStudio.getState()
  const [strategies, setStrategies] = useState<{ capture: Strategy[]; actuator: Strategy[]; capture_default: string | null } | null>(null)
  const [python, setPython] = useState('')
  const [dirty, setDirty] = useState(false)
  // text fields are uncontrolled: remount them when another file is loaded or reverted
  const [gen, setGen] = useState(0)

  useEffect(() => {
    api.strategies().then(setStrategies, () => undefined)
    window.studio.prefs().then((p) => setPython(p.pythonPath))
  }, [])

  if (!config) return null
  const c = config.config

  const set = async (path: string, value: unknown) => {
    try {
      setConfig(await api.patchConfig({ [path]: value }))
      setDirty(true)
    } catch (e) {
      toast({ kind: 'error', title: 'Setting rejected', body: (e as Error).message })
    }
  }
  const str = (p: string) => String(get(c, p) ?? '')
  const tiers = (get(c, 'grounding.tiers') as string[]) ?? []

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-line bg-panel px-6 py-4">
        <div className="min-w-0">
          <h2 className="text-[16px] font-semibold">Settings</h2>
          <p className="text-[12px] text-muted">
            The session config: the same file the CLI, the Python API and Robot Framework read. Changes apply to the next analysis.
          </p>
          <div className="mt-1.5 flex min-w-0 items-center gap-2">
            <FileJson size={14} className="shrink-0 text-accent" />
            <code className="selectable truncate font-mono text-[12px]" title={config.path}>
              {config.path}
            </code>
            {!config.exists && <Badge tone="warn">not saved yet: defaults</Badge>}
            {dirty && <Badge tone="warn">unsaved changes</Badge>}
          </div>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <Button
            icon={<FolderOpen size={14} />}
            onClick={async () => {
              if (dirty && !confirm('Discard the unsaved changes and open another config?')) return
              if (await openConfig()) {
                setDirty(false)
                setGen((g) => g + 1)
              }
            }}
            title="Use another session config file (remembered for the next launch)"
          >
            Open…
          </Button>
          <Button icon={<FilePlus2 size={14} />} onClick={async () => (await saveConfigAs()) && setDirty(false)}>
            Save as…
          </Button>
          <Button
            icon={<RotateCcw size={14} />}
            disabled={!dirty}
            title="Re-read the file and drop the unsaved changes"
            onClick={async () => {
              setConfig(await api.reloadConfig())
              setDirty(false)
              setGen((g) => g + 1)
            }}
          >
            Revert
          </Button>
          <Button
            variant="primary"
            icon={<Save size={14} />}
            onClick={async () => {
              try {
                setConfig(await api.saveConfig())
                setDirty(false)
                toast({ kind: 'ok', title: 'Configuration saved', body: config.path })
              } catch (e) {
                toast({ kind: 'error', title: 'Could not save', body: (e as Error).message })
              }
            }}
          >
            Save
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div key={`${config.path}#${gen}`} className="mx-auto max-w-3xl space-y-8 px-6 py-6">
          <Section title="Element detection" body="Finds the boxes on the screen.">
            <Field label="Detector" hint="Changing it reloads the models on the next analysis.">
              <Select value={str('detector.backend')} onChange={(v) => set('detector.backend', v)} options={DETECTORS} className="w-full" />
            </Field>
            {str('detector.backend') === 'grpc' && (
              <Field label="Detector service" hint="host:port of a running detector (Services).">
                <Input defaultValue={str('detector.grpc_target')} onBlur={(e) => set('detector.grpc_target', e.target.value)} className="w-full" />
              </Field>
            )}
            {str('detector.backend') === 'modular' && (
              <Field label="Contour pass" hint="A second look for dim, isolated icons the region model missed.">
                <Switch checked={Boolean(get(c, 'detector.contour_pass'))} onChange={(v) => set('detector.contour_pass', v)} />
              </Field>
            )}
            {str('detector.backend') === 'modular' && (
              <Field label="Icon library" hint="Folder with icons.json and the project's own icon images; matching icons get their name from it.">
                <Input defaultValue={str('detector.icon_library')} onBlur={(e) => set('detector.icon_library', e.target.value || null)} className="w-full" />
              </Field>
            )}
            <Field label="Use the GPU" hint="When one is available.">
              <Switch checked={Boolean(get(c, 'detector.use_gpu'))} onChange={(v) => set('detector.use_gpu', v)} />
            </Field>
          </Section>

          <Section title="Text" body="Reads the captions: what text= locators match.">
            <Field label="OCR engine">
              <Select value={str('ocr.engine')} onChange={(v) => set('ocr.engine', v)} options={OCR} className="w-full" />
            </Field>
            <Field label="Upscale small text" hint="Re-reads small captions at a higher resolution.">
              <Switch checked={Boolean(get(c, 'ocr.upscale'))} onChange={(v) => set('ocr.upscale', v)} />
            </Field>
            <Field label="Retry low-confidence text" hint="A second engine re-reads uncertain boxes.">
              <Switch checked={Boolean(get(c, 'ocr.retry_low_confidence'))} onChange={(v) => set('ocr.retry_low_confidence', v)} />
            </Field>
          </Section>

          <Section title="Capture" body="Where screenshots come from.">
            <Field label="Capture source" hint={`Default on this machine: ${strategies?.capture_default ?? '…'}`}>
              <Select
                value={str('capture.strategy')}
                onChange={(v) => set('capture.strategy', v || null)}
                className="w-full"
                options={[
                  { value: '', label: 'Automatic' },
                  ...(strategies?.capture ?? []).map((s) => ({
                    value: s.name,
                    label: `${s.name}: ${s.description}${s.available ? '' : ' (not available)'}`,
                    disabled: !s.available
                  }))
                ]}
              />
            </Field>
            <Field label="Camera mode" hint="Rectify a screen photographed by a camera.">
              <Switch checked={Boolean(get(c, 'capture.camera_mode'))} onChange={(v) => set('capture.camera_mode', v)} />
            </Field>
          </Section>

          <Section title="Description locators (desc=)" body="How a plain-language description is grounded (ADR-022).">
            <Field label="Tiers, in order" hint="Lexical scoring first; a model only for the tail. Verification stays lexical.">
              <div className="flex flex-wrap gap-1.5">
                {TIERS.map((t) => {
                  const on = tiers.includes(t)
                  return (
                    <button
                      key={t}
                      onClick={() => set('grounding.tiers', on ? tiers.filter((x) => x !== t) : [...tiers, t])}
                      className={clsx(
                        'h-7 rounded-md border px-2.5 font-mono text-[12px]',
                        on ? 'border-accent bg-accent/15 text-accent' : 'border-line text-muted hover:bg-raised'
                      )}
                    >
                      {on && <span className="mr-1 text-faint">{tiers.indexOf(t) + 1}</span>}
                      {t}
                    </button>
                  )
                })}
              </div>
            </Field>
            <Field label="Text model" hint="Ollama tag for the slm tier.">
              <Input defaultValue={str('grounding.model')} onBlur={(e) => set('grounding.model', e.target.value)} className="w-full" />
            </Field>
            <Field label="Vision model" hint="Ollama tag for the vlm tier.">
              <Input defaultValue={str('grounding.vision_model')} onBlur={(e) => set('grounding.vision_model', e.target.value)} className="w-full" />
            </Field>
          </Section>

          <Section title="Refinement" body="An optional small model reviews the DOM after detection.">
            <Field label="Refine with a model">
              <Switch checked={Boolean(get(c, 'refiner.enabled'))} onChange={(v) => set('refiner.enabled', v)} />
            </Field>
            {Boolean(get(c, 'refiner.enabled')) && (
              <Field label="Model">
                <Input defaultValue={str('refiner.model')} onBlur={(e) => set('refiner.model', e.target.value)} className="w-full" />
              </Field>
            )}
          </Section>

          <Section title="Actuation" body="How Try click delivers input (ADR-019).">
            <Field label="Actuator">
              <Select
                value={str('actuator.strategy')}
                onChange={(v) => set('actuator.strategy', v || null)}
                className="w-full"
                options={[
                  { value: '', label: 'Platform default' },
                  ...(strategies?.actuator ?? []).map((s) => ({
                    value: s.name,
                    label: `${s.name}: ${s.description}${s.available ? '' : ' (not available)'}`,
                    disabled: !s.available
                  }))
                ]}
              />
            </Field>
            {str('actuator.strategy') === 'grpc' && (
              <Field label="Actuator service" hint="host:port">
                <Input defaultValue={str('actuator.target')} onBlur={(e) => set('actuator.target', e.target.value)} className="w-full" />
              </Field>
            )}
          </Section>

          <Section title="Studio" body="This app, not the pipeline.">
            <Field label="Python interpreter" hint="Needs VizDOM's dependencies. Changing it restarts the bridge.">
              <Input value={python} onChange={(e) => setPython(e.target.value)} className="flex-1" />
              <Button
                icon={<FolderOpen size={14} />}
                onClick={async () => {
                  const p = await window.studio.pickPython()
                  if (p) setPython(p)
                }}
              >
                Browse
              </Button>
              <Button onClick={() => window.studio.restartBridge(python)}>Apply</Button>
            </Field>
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ title, body, children }: { title: string; body: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-[14px] font-semibold">{title}</h3>
      <p className="text-[12px] text-muted">{body}</p>
      <div className="mt-2 divide-y divide-line rounded-xl border border-line bg-panel px-4">{children}</div>
    </section>
  )
}
