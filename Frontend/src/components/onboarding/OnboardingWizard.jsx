'use client';

// ============================================================
// FILE: src/components/onboarding/OnboardingWizard.jsx
//
// Everything the agents need, asked once, in six short steps.
// Each step says what the answer is used for, so a farmer knows
// why FarmXpert asks. A draft is kept in this browser tab, so a
// dropped connection or a phone call does not lose the answers.
//
// Saved in one request (POST /onboarding, one transaction): no
// half-made farm is ever left behind.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  ArrowLeft, ArrowRight, Check, CheckCircle2, Cpu, Droplets, FlaskConical, Loader2, LocateFixed,
  MapPin, Minus, Plus, Sprout, Tractor, User, Wifi,
} from 'lucide-react';

import { useRouter } from '@/i18n/navigation';
import { ApiError, api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { useAuth } from '@/context/AuthContext';
import Botanical from '@/components/ui/Botanical';
import Logo from '@/components/ui/Logo';
import { ThemeToggle } from '@/components/theme/ThemeProvider';
import {
  Alert, Button, ChoiceChips, Eyebrow, SelectField, TextField, inputClass,
} from '@/components/ui/primitives';

const DRAFT_KEY = 'fx.onboarding.draft';
const STEPS = [
  { id: 'you', icon: User },
  { id: 'farm', icon: MapPin },
  { id: 'crop', icon: Sprout },
  { id: 'soil', icon: FlaskConical },
  { id: 'resources', icon: Tractor },
  { id: 'device', icon: Cpu },
];
export const INDIAN_STATES = ['Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa', 'Gujarat',
  'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
  'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands', 'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry'];

const EMPTY = {
  profile: { name: '', phone: '', language: '' },
  farm: { name: '', latitude: '', longitude: '', area: '', unit: 'acres', state: '', district: '', address: '', water_source: '' },
  field: { crop_name: '', growth_stage: '', sown_on: '', expected_harvest_on: '', irrigation_method: '', soil_type: '' },
  soil: { has_test: null, unit: 'card', soil_ph: '', nitrogen: '', phosphorus: '', potassium: '', soil_moisture: '', electrical_conductivity: '' },
  resources: { labor_units_available: 2, equipment_available: [], budget_available: '', working_hours_start: '06:00', working_hours_end: '18:00' },
  device: { token: '', label: 'Soil probe' },
};

function readDraft() {
  try {
    const raw = window.sessionStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function writeDraft(value) {
  try {
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(value));
  } catch {
    /* storage unavailable: the form still works, only without a draft */
  }
}

const num = (v) => (v === '' || v === null || v === undefined || Number.isNaN(Number(v)) ? undefined : Number(v));
const ACRES_PER_HECTARE = 2.47105;
const BIGHA_PER_ACRE = 1.6;          // Gujarat/Rajasthan pucca bigha ≈ 0.625 acre

export default function OnboardingWizard() {
  const t = useTranslations('onboarding');
  const o = useTranslations('options');
  const locale = useLocale();
  const router = useRouter();
  const { user, reload } = useAuth();
  const [step, setStep] = useState(0);
  const [data, setData] = useState(EMPTY);
  const [options, setOptions] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [saving, setSaving] = useState(false);

  // Restore the draft, then the choices the backend understands.
  useEffect(() => {
    const draft = readDraft();
    setData((d) => ({
      ...(draft?.data || d),
      profile: { ...(draft?.data?.profile || d.profile), name: draft?.data?.profile?.name || user?.name || '',
        phone: draft?.data?.profile?.phone || user?.phone || '', language: draft?.data?.profile?.language || user?.language || locale },
    }));
    if (draft?.step) setStep(Math.min(draft.step, STEPS.length - 1));
    api.get('/onboarding').then((res) => {
      if (res.onboarded) router.replace('/dashboard');
      setOptions(res.options);
    }).catch(() => setOptions(null));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { writeDraft({ step, data }); }, [step, data]);

  const set = useCallback((section, key, value) => {
    setData((d) => ({ ...d, [section]: { ...d[section], [key]: value } }));
    setErrors((e) => ({ ...e, [`${section}.${key}`]: undefined }));
  }, []);

  const opt = (group, values) => (values || []).map((value) => ({ value, label: o(`${group}.${value}`) }));

  // ── validation per step ────────────────────────────────────────────
  const validate = (index) => {
    const e = {};
    const f = data.farm;
    if (STEPS[index].id === 'you') {
      if (data.profile.name.trim().length < 2) e['profile.name'] = t('errors.name');
      if (data.profile.phone && !/^[0-9+][0-9]{7,14}$/.test(data.profile.phone.replace(/\s/g, ''))) e['profile.phone'] = t('errors.phone');
    }
    if (STEPS[index].id === 'farm') {
      if (!f.name.trim()) e['farm.name'] = t('errors.farmName');
      const lat = num(f.latitude);
      const lon = num(f.longitude);
      if (lat === undefined || lat < 6 || lat > 38 || lon === undefined || lon < 68 || lon > 98) e['farm.location'] = t('errors.location');
      if (!(num(f.area) > 0)) e['farm.area'] = t('errors.area');
      if (!f.state) e['farm.state'] = t('errors.state');
      if (!f.district.trim()) e['farm.district'] = t('errors.district');
    }
    if (STEPS[index].id === 'crop') {
      if (!data.field.soil_type) e['field.soil_type'] = t('errors.soilType');
      if (data.field.sown_on && data.field.sown_on > new Date().toISOString().slice(0, 10)) e['field.sown_on'] = t('errors.sownFuture');
      if (data.field.sown_on && data.field.expected_harvest_on && data.field.expected_harvest_on < data.field.sown_on) {
        e['field.expected_harvest_on'] = t('errors.harvestBeforeSowing');
      }
    }
    if (STEPS[index].id === 'soil' && data.soil.has_test) {
      const ph = num(data.soil.soil_ph);
      if (data.soil.soil_ph !== '' && (ph === undefined || ph < 0 || ph > 14)) e['soil.soil_ph'] = t('errors.ph');
    }
    if (STEPS[index].id === 'device' && data.device.token && !/^[A-Za-z0-9_-]{8,100}$/.test(data.device.token.trim())) {
      e['device.token'] = t('errors.token');
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const next = () => {
    if (!validate(step)) return;
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const acres = useMemo(() => {
    const a = num(data.farm.area);
    if (a === undefined) return undefined;
    return data.farm.unit === 'hectares' ? a * ACRES_PER_HECTARE : data.farm.unit === 'bigha' ? a / BIGHA_PER_ACRE : a;
  }, [data.farm.area, data.farm.unit]);

  const submit = async () => {
    for (let i = 0; i < STEPS.length; i += 1) {
      if (!validate(i)) {
        setStep(i);
        return;
      }
    }
    setSaving(true);
    setSubmitError(null);
    const f = data.farm;
    const s = data.soil;
    const r = data.resources;
    const soil = s.has_test ? soilForAgents(s) : null;
    try {
      await api.post('/onboarding', {
        profile: {
          name: data.profile.name.trim(),
          ...(data.profile.phone && { phone: data.profile.phone.replace(/\s/g, '') }),
          language: data.profile.language || locale,
        },
        farm: {
          name: f.name.trim(), latitude: num(f.latitude), longitude: num(f.longitude),
          area_acres: Math.round(acres * 100) / 100, state: f.state, district: f.district.trim(),
          ...(f.address.trim() && { address: f.address.trim() }),
          ...(f.water_source && { water_source: f.water_source }),
          resources: {
            irrigation_available: data.field.irrigation_method !== 'rainfed' && f.water_source !== 'rainfed',
            labor_units_available: r.labor_units_available,
            equipment_available: r.equipment_available,
            ...(num(r.budget_available) !== undefined && { budget_available: num(r.budget_available) }),
            working_hours_start: r.working_hours_start, working_hours_end: r.working_hours_end,
          },
        },
        field: Object.fromEntries(Object.entries({
          name: t('defaultFieldName'), ...data.field,
        }).filter(([, v]) => v !== '' && v !== null)),
        ...(soil && Object.keys(soil).length && { soil: { source: 'lab', ...soil } }),
        ...(data.device.token.trim() && { device: { token: data.device.token.trim(), label: data.device.label || 'Soil probe' } }),
      });
      try { window.sessionStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
      await reload();
      router.replace('/dashboard?welcome=1');
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'network';
      setSubmitError(t.has(`submitErrors.${code}`) ? t(`submitErrors.${code}`) : t('submitErrors.generic'));
    } finally {
      setSaving(false);
    }
  };

  const current = STEPS[step];
  const last = step === STEPS.length - 1;
  const progress = Math.round(((step + 1) / STEPS.length) * 100);

  return (
    <div className="min-h-dvh">
      {/* top bar */}
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="container-app flex h-16 items-center justify-between">
          <Logo href="/" />
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-muted sm:inline">{t('progress', { percent: progress })}</span>
            <ThemeToggle compact />
          </div>
        </div>
        <div className="h-0.5 bg-line">
          <div className="h-full bg-gradient-to-r from-leaf to-gold transition-[width] duration-700 ease-out" style={{ width: `${progress}%` }} />
        </div>
      </header>

      <div className="container-app grid gap-8 py-8 lg:grid-cols-[18rem_minmax(0,1fr)] lg:gap-12 lg:py-12">
        {/* step rail */}
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <div className="panel-forest hidden rounded-[1.75rem] p-7 lg:block">
            <div className="pointer-events-none absolute inset-3 rounded-[1.4rem] border border-gold/20" aria-hidden />
            <Botanical name="sprig" className="animate-sway -right-16 -bottom-20 w-52 -scale-x-100 opacity-25" />
            <p className="relative font-script text-4xl text-gold">{t('railScript')}</p>
            <p className="relative mt-1 text-sm text-white/65">{t('railLead')}</p>
            <ol className="relative mt-7 space-y-1">
              {STEPS.map((s, i) => {
                const done = i < step;
                const active = i === step;
                return (
                  <li key={s.id}>
                    <button type="button" onClick={() => (i < step ? setStep(i) : null)} disabled={i > step}
                      className={cn('flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition-colors',
                        active ? 'bg-white/12 text-white' : done ? 'text-white/80 hover:bg-white/6' : 'text-white/40')}>
                      <span className={cn('grid size-8 shrink-0 place-items-center rounded-full border',
                        done ? 'border-gold bg-gold text-forest-deep' : active ? 'border-gold text-gold' : 'border-white/20')}>
                        {done ? <Check className="size-4" /> : <s.icon className="size-4" />}
                      </span>
                      {t(`steps.${s.id}.short`)}
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
          {/* phone: a compact dot row */}
          <div className="flex items-center justify-center gap-2 lg:hidden" aria-hidden>
            {STEPS.map((s, i) => (
              <span key={s.id} className={cn('h-1.5 rounded-full transition-all duration-500',
                i === step ? 'w-8 bg-gold' : i < step ? 'w-3 bg-leaf' : 'w-3 bg-line')} />
            ))}
          </div>
        </aside>

        {/* step */}
        <main className="min-w-0">
          <div key={current.id} className="animate-rise">
            <Eyebrow className="justify-start" line={false}>{t('stepOf', { step: step + 1, total: STEPS.length })}</Eyebrow>
            <h1 className="mt-3 text-3xl leading-tight text-forest sm:text-4xl dark:text-ink">
              {t(`steps.${current.id}.title`)}{' '}
              <span className="font-script text-4xl font-normal text-gold sm:text-5xl">{t(`steps.${current.id}.script`)}</span>
            </h1>
            <p className="mt-3 max-w-2xl text-[0.95rem] leading-relaxed text-muted">{t(`steps.${current.id}.lead`)}</p>

            <div className="mt-8 rounded-[1.75rem] border border-line bg-surface p-6 shadow-card sm:p-8">
              {current.id === 'you' && <StepYou data={data} set={set} errors={errors} t={t} />}
              {current.id === 'farm' && <StepFarm data={data} set={set} errors={errors} t={t} opt={opt} options={options} acres={acres} />}
              {current.id === 'crop' && <StepCrop data={data} set={set} errors={errors} t={t} o={o} opt={opt} options={options} />}
              {current.id === 'soil' && <StepSoil data={data} set={set} errors={errors} t={t} />}
              {current.id === 'resources' && <StepResources data={data} set={set} t={t} opt={opt} options={options} />}
              {current.id === 'device' && <StepDevice data={data} set={set} errors={errors} t={t} />}
            </div>

            <WhyWeAsk text={t(`steps.${current.id}.why`)} label={t('whyLabel')} />
            <Alert className="mt-5">{submitError}</Alert>

            <div className="mt-8 flex items-center justify-between gap-3">
              <Button variant="ghost" onClick={back} disabled={step === 0} className={step === 0 ? 'invisible' : ''}>
                <ArrowLeft className="size-4" aria-hidden />{t('back')}
              </Button>
              <div className="flex items-center gap-3">
                {['soil', 'resources', 'device'].includes(current.id) && !last && (
                  <Button variant="ghost" onClick={() => setStep((s) => s + 1)}>{t('skip')}</Button>
                )}
                {last ? (
                  <Button onClick={submit} loading={saving} size="lg">
                    <CheckCircle2 className="size-4.5" aria-hidden />{t('finish')}
                  </Button>
                ) : (
                  <Button onClick={next} size="lg">{t('continue')}<ArrowRight className="size-4" aria-hidden /></Button>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function WhyWeAsk({ text, label }) {
  return (
    <div className="mt-5 flex items-start gap-3 rounded-2xl border border-gold/25 bg-gold-soft/40 px-5 py-4 text-sm leading-relaxed text-ink">
      <Sprout className="mt-0.5 size-4.5 shrink-0 text-gold" aria-hidden />
      <p><span className="font-medium">{label}</span> {text}</p>
    </div>
  );
}

const err = (errors, key) => errors[key];

// ── step 1: you ─────────────────────────────────────────────────────────────

function StepYou({ data, set, errors, t }) {
  const languages = [
    ['en', 'English'], ['hi', 'हिन्दी'], ['gu', 'ગુજરાતી'], ['mr', 'मराठी'], ['pa', 'ਪੰਜਾਬੀ'],
    ['ta', 'தமிழ்'], ['te', 'తెలుగు'], ['kn', 'ಕನ್ನಡ'], ['bn', 'বাংলা'], ['ml', 'മലയാളം'], ['or', 'ଓଡ଼ିଆ'],
  ];
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <TextField label={t('fields.name')} value={data.profile.name} autoComplete="name"
        onChange={(e) => set('profile', 'name', e.target.value)} error={err(errors, 'profile.name')} />
      <TextField label={t('fields.phone')} optional={t('optional')} type="tel" inputMode="tel" autoComplete="tel"
        placeholder="+91 98765 43210" value={data.profile.phone}
        onChange={(e) => set('profile', 'phone', e.target.value)} error={err(errors, 'profile.phone')} hint={t('fields.phoneHint')} />
      <div className="sm:col-span-2">
        <p className="mb-2.5 text-sm font-medium">{t('fields.language')}</p>
        <ChoiceChips label={t('fields.language')} value={data.profile.language}
          onChange={(v) => set('profile', 'language', v)} options={languages.map(([value, label]) => ({ value, label }))} />
        <p className="mt-2.5 text-xs text-faint">{t('fields.languageHint')}</p>
      </div>
    </div>
  );
}

// ── step 2: farm ────────────────────────────────────────────────────────────

function StepFarm({ data, set, errors, t, opt, options, acres }) {
  const f = data.farm;
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState(null);

  const locate = () => {
    if (!navigator.geolocation) {
      setLocateError(t('fields.gpsUnsupported'));
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        set('farm', 'latitude', pos.coords.latitude.toFixed(5));
        set('farm', 'longitude', pos.coords.longitude.toFixed(5));
        setLocating(false);
      },
      () => {
        setLocateError(t('fields.gpsDenied'));
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  };

  const hasPoint = f.latitude !== '' && f.longitude !== '';

  return (
    <div className="space-y-6">
      <TextField label={t('fields.farmName')} placeholder={t('fields.farmNamePlaceholder')} value={f.name}
        onChange={(e) => set('farm', 'name', e.target.value)} error={err(errors, 'farm.name')} />

      <div className="rounded-2xl border border-line bg-canvas/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">{t('fields.location')}</p>
            <p className="mt-0.5 text-xs text-faint">{t('fields.locationHint')}</p>
          </div>
          <Button variant={hasPoint ? 'outline' : 'primary'} size="sm" onClick={locate} loading={locating}>
            <LocateFixed className="size-4" aria-hidden />{hasPoint ? t('fields.gpsAgain') : t('fields.gps')}
          </Button>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <TextField label={t('fields.latitude')} inputMode="decimal" placeholder="21.17024" value={f.latitude}
            onChange={(e) => set('farm', 'latitude', e.target.value.replace(/[^\d.-]/g, ''))} />
          <TextField label={t('fields.longitude')} inputMode="decimal" placeholder="72.83106" value={f.longitude}
            onChange={(e) => set('farm', 'longitude', e.target.value.replace(/[^\d.-]/g, ''))} />
        </div>
        {hasPoint && !err(errors, 'farm.location') && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-leaf">
            <CheckCircle2 className="size-3.5" aria-hidden />{t('fields.locationSet')}
          </p>
        )}
        {(locateError || err(errors, 'farm.location')) && (
          <p className="mt-3 text-xs text-danger">{locateError || err(errors, 'farm.location')}</p>
        )}
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField label={t('fields.state')} value={f.state} placeholder={t('fields.choose')}
          options={INDIAN_STATES.map((s) => ({ value: s, label: s }))}
          onChange={(e) => set('farm', 'state', e.target.value)} error={err(errors, 'farm.state')} />
        <TextField label={t('fields.district')} value={f.district} placeholder={t('fields.districtPlaceholder')}
          onChange={(e) => set('farm', 'district', e.target.value)} error={err(errors, 'farm.district')} />
      </div>

      <div>
        <p className="mb-1.5 text-sm font-medium">{t('fields.area')}</p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input className={cn(inputClass, 'sm:max-w-44')} inputMode="decimal" placeholder="5" value={f.area}
            aria-label={t('fields.area')} aria-invalid={err(errors, 'farm.area') ? 'true' : undefined}
            onChange={(e) => set('farm', 'area', e.target.value.replace(/[^\d.]/g, ''))} />
          <ChoiceChips label={t('fields.unit')} value={f.unit} onChange={(v) => set('farm', 'unit', v)}
            options={['acres', 'hectares', 'bigha'].map((u) => ({ value: u, label: t(`fields.units.${u}`) }))} />
        </div>
        {err(errors, 'farm.area') ? <p className="mt-1.5 text-xs text-danger">{err(errors, 'farm.area')}</p>
          : acres !== undefined && f.unit !== 'acres' && (
            <p className="mt-1.5 text-xs text-faint">{t('fields.areaAcres', { acres: acres.toFixed(2) })}</p>
          )}
      </div>

      <div>
        <p className="mb-2.5 flex items-center gap-2 text-sm font-medium"><Droplets className="size-4 text-sky" aria-hidden />{t('fields.water')}</p>
        <ChoiceChips label={t('fields.water')} value={f.water_source} onChange={(v) => set('farm', 'water_source', v)}
          options={opt('water', options?.water_sources)} />
      </div>
    </div>
  );
}

// ── step 3: crop ────────────────────────────────────────────────────────────

const SOIL_SWATCH = {
  black_cotton: '#2b2622', alluvial: '#a88a5f', red_laterite: '#9c4a2c', loamy: '#6b5033', sandy_loam: '#c3a26d',
  sandy: '#dcc594', clay_loam: '#7a5a41', clay: '#8a6a55', silt: '#9b8b73', peaty: '#3d3326',
};

function StepCrop({ data, set, errors, t, o, opt, options }) {
  const fl = data.field;
  const [other, setOther] = useState(false);
  const crops = options?.crops || [];
  return (
    <div className="space-y-7">
      <div>
        <p className="mb-2.5 text-sm font-medium">{t('fields.crop')}</p>
        <div className="flex flex-wrap gap-2">
          {crops.map((c) => (
            <button key={c} type="button" aria-pressed={fl.crop_name === c} onClick={() => { setOther(false); set('field', 'crop_name', c); }}
              className={cn('rounded-full border px-3.5 py-1.5 text-sm transition-all',
                fl.crop_name === c ? 'border-forest bg-forest text-on-forest shadow-card' : 'border-line bg-surface text-muted hover:border-leaf/50 hover:text-ink')}>
              {o(`crops.${c}`)}
            </button>
          ))}
          <button type="button" onClick={() => { setOther(true); set('field', 'crop_name', ''); }}
            className={cn('rounded-full border border-dashed px-3.5 py-1.5 text-sm',
              other ? 'border-forest text-forest dark:text-leaf' : 'border-line text-faint hover:text-ink')}>
            {t('fields.otherCrop')}
          </button>
        </div>
        {other && (
          <TextField className="mt-3 max-w-sm" placeholder={t('fields.otherCropPlaceholder')} value={fl.crop_name} autoFocus
            onChange={(e) => set('field', 'crop_name', e.target.value.toLowerCase())} />
        )}
        <p className="mt-2 text-xs text-faint">{t('fields.cropHint')}</p>
      </div>

      <div>
        <p className="mb-2.5 text-sm font-medium">{t('fields.stage')}</p>
        <ChoiceChips label={t('fields.stage')} value={fl.growth_stage} onChange={(v) => set('field', 'growth_stage', v)}
          options={opt('stages', options?.growth_stages)} />
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <TextField label={t('fields.sownOn')} type="date" max={new Date().toISOString().slice(0, 10)} value={fl.sown_on}
          onChange={(e) => set('field', 'sown_on', e.target.value)} error={err(errors, 'field.sown_on')} optional={t('optional')} />
        <TextField label={t('fields.harvestOn')} type="date" value={fl.expected_harvest_on}
          onChange={(e) => set('field', 'expected_harvest_on', e.target.value)} error={err(errors, 'field.expected_harvest_on')} optional={t('optional')} />
      </div>

      <div>
        <p className="mb-1 text-sm font-medium">{t('fields.soilType')}</p>
        <p className="mb-3 text-xs text-faint">{t('fields.soilTypeHint')}</p>
        <div role="radiogroup" aria-label={t('fields.soilType')} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {(options?.soil_types || []).map((s) => (
            <button key={s} type="button" role="radio" aria-checked={fl.soil_type === s} onClick={() => set('field', 'soil_type', s)}
              className={cn('group flex flex-col items-start gap-2.5 rounded-2xl border p-3 text-left transition-all',
                fl.soil_type === s ? 'border-forest bg-sage shadow-card ring-2 ring-forest/15 dark:border-leaf' : 'border-line bg-surface hover:border-leaf/40')}>
              <span className="h-8 w-full rounded-lg shadow-inner" style={{ background: `radial-gradient(circle at 30% 30%, ${SOIL_SWATCH[s]}cc, ${SOIL_SWATCH[s]})` }} aria-hidden />
              <span className="text-sm leading-tight font-medium">{o(`soils.${s}`)}</span>
            </button>
          ))}
        </div>
        {err(errors, 'field.soil_type') && <p className="mt-2 text-xs text-danger">{err(errors, 'field.soil_type')}</p>}
      </div>

      <div>
        <p className="mb-2.5 text-sm font-medium">{t('fields.irrigation')}</p>
        <ChoiceChips label={t('fields.irrigation')} value={fl.irrigation_method} onChange={(v) => set('field', 'irrigation_method', v)}
          options={opt('irrigation', options?.irrigation_methods)} />
      </div>
    </div>
  );
}

// ── step 4: soil test ───────────────────────────────────────────────────────

// The soil agent works in mg/kg (lab / sensor). Most Indian farmers hold a
// Soil Health Card in kg/ha. Phosphorus (Olsen) and potassium (NH4OAc) are the
// same tests, so kg/ha / 2.24 = mg/kg for a 15 cm plough layer. The card's
// nitrogen is a different test (alkaline permanganate) that cannot be
// converted to mineral N, so from a card it is not sent - better no value
// than one 5-10x too high, which would drive the wrong fertiliser advice.
const KG_HA_PER_MG_KG = 2.24;

const SOIL_FIELDS = {
  card: [['soil_ph', '6.5 - 7.5', 'ph'], ['nitrogen', '280 - 560', 'kgHa'], ['phosphorus', '11 - 25', 'kgHa'],
    ['potassium', '110 - 280', 'kgHa'], ['electrical_conductivity', '< 1', 'dsm'], ['soil_moisture', '20 - 40', 'percent']],
  lab: [['soil_ph', '6.5 - 7.5', 'ph'], ['nitrogen', '30 - 90', 'mgKg'], ['phosphorus', '10 - 25', 'mgKg'],
    ['potassium', '55 - 140', 'mgKg'], ['electrical_conductivity', '< 1', 'dsm'], ['soil_moisture', '20 - 40', 'percent']],
};

/** The reading in the units the soil agent uses. */
export function soilForAgents(s) {
  const card = s.unit === 'card';
  const out = {};
  for (const key of ['soil_ph', 'soil_moisture', 'electrical_conductivity']) {
    if (num(s[key]) !== undefined) out[key] = num(s[key]);
  }
  for (const key of ['phosphorus', 'potassium']) {
    const v = num(s[key]);
    if (v !== undefined) out[key] = card ? Math.round((v / KG_HA_PER_MG_KG) * 10) / 10 : v;
  }
  if (!card && num(s.nitrogen) !== undefined) out.nitrogen = num(s.nitrogen);
  return out;
}

function StepSoil({ data, set, errors, t }) {
  const s = data.soil;
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2">
        {[
          [true, FlaskConical, t('fields.hasTest'), t('fields.hasTestHint')],
          [false, Sprout, t('fields.noTest'), t('fields.noTestHint')],
        ].map(([value, Icon, title, hint]) => (
          <button key={String(value)} type="button" role="radio" aria-checked={s.has_test === value}
            onClick={() => set('soil', 'has_test', value)}
            className={cn('flex items-start gap-4 rounded-2xl border p-5 text-left transition-all',
              s.has_test === value ? 'border-forest bg-sage shadow-card dark:border-leaf' : 'border-line bg-surface hover:border-leaf/40')}>
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-raised shadow-card"><Icon className="size-5 text-leaf" /></span>
            <span><span className="block font-medium">{title}</span><span className="mt-1 block text-sm text-muted">{hint}</span></span>
          </button>
        ))}
      </div>
      {s.has_test && (
        <div className="space-y-5 animate-rise">
          <div>
            <p className="mb-2.5 text-sm font-medium">{t('fields.reportType')}</p>
            <ChoiceChips label={t('fields.reportType')} value={s.unit} onChange={(v) => set('soil', 'unit', v)}
              options={[{ value: 'card', label: t('fields.reportCard') }, { value: 'lab', label: t('fields.reportLab') }]} />
            {s.unit === 'card' && <p className="mt-2.5 text-xs leading-relaxed text-faint">{t('fields.cardNote')}</p>}
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {SOIL_FIELDS[s.unit].map(([key, typical, unit]) => (
              <TextField key={key} label={`${t(`soilFields.${key}`)} (${t(`units.${unit}`)})`} inputMode="decimal"
                placeholder={typical} value={s[key]} hint={t('fields.typical', { range: typical })}
                onChange={(e) => set('soil', key, e.target.value.replace(/[^\d.]/g, ''))} error={err(errors, `soil.${key}`)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── step 5: resources ───────────────────────────────────────────────────────

function StepResources({ data, set, t, opt, options }) {
  const r = data.resources;
  return (
    <div className="space-y-7">
      <div>
        <p className="mb-2.5 text-sm font-medium">{t('fields.labour')}</p>
        <div className="inline-flex items-center gap-1 rounded-full border border-line bg-canvas p-1">
          <button type="button" aria-label={t('fields.less')} onClick={() => set('resources', 'labor_units_available', Math.max(0, r.labor_units_available - 1))}
            className="grid size-10 place-items-center rounded-full hover:bg-sage"><Minus className="size-4" /></button>
          <span className="min-w-14 text-center font-serif text-2xl" aria-live="polite">{r.labor_units_available}</span>
          <button type="button" aria-label={t('fields.more')} onClick={() => set('resources', 'labor_units_available', Math.min(500, r.labor_units_available + 1))}
            className="grid size-10 place-items-center rounded-full hover:bg-sage"><Plus className="size-4" /></button>
        </div>
        <p className="mt-2 text-xs text-faint">{t('fields.labourHint')}</p>
      </div>
      <div>
        <p className="mb-2.5 text-sm font-medium">{t('fields.equipment')}</p>
        <ChoiceChips multiple label={t('fields.equipment')} values={r.equipment_available}
          onChange={(v) => set('resources', 'equipment_available', v)} options={opt('equipment', options?.equipment)} />
      </div>
      <div className="grid gap-5 sm:grid-cols-3">
        <TextField label={t('fields.budget')} optional={t('optional')} inputMode="numeric" placeholder="10000" value={r.budget_available}
          onChange={(e) => set('resources', 'budget_available', e.target.value.replace(/\D/g, ''))} hint={t('fields.budgetHint')} />
        <TextField label={t('fields.workStart')} type="time" value={r.working_hours_start}
          onChange={(e) => set('resources', 'working_hours_start', e.target.value)} />
        <TextField label={t('fields.workEnd')} type="time" value={r.working_hours_end}
          onChange={(e) => set('resources', 'working_hours_end', e.target.value)} />
      </div>
    </div>
  );
}

// ── step 6: Blynk device ────────────────────────────────────────────────────

function StepDevice({ data, set, errors, t }) {
  const d = data.device;
  const [test, setTest] = useState(null);     // null | 'testing' | {ok, reading} | {error}
  const check = async () => {
    setTest('testing');
    try {
      setTest(await api.post('/onboarding/device', { token: d.token.trim() }));
    } catch (e) {
      setTest({ error: e.code === 'invalid_device_token' ? t('fields.tokenRejected') : t('fields.deviceUnreachable') });
    }
  };
  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4 rounded-2xl bg-sage/70 p-5">
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-raised shadow-card"><Wifi className="size-5 text-leaf" /></span>
        <p className="text-sm leading-relaxed text-muted">{t('fields.deviceIntro')}</p>
      </div>
      <div className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_14rem]">
        <TextField label={t('fields.token')} placeholder="aBcD1234efGH5678…" value={d.token} autoComplete="off" spellCheck={false}
          onChange={(e) => { set('device', 'token', e.target.value.trim()); setTest(null); }} error={err(errors, 'device.token')}
          hint={t('fields.tokenHint')} />
        <TextField label={t('fields.deviceName')} value={d.label} onChange={(e) => set('device', 'label', e.target.value)} />
      </div>
      {d.token.length >= 8 && (
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="outline" size="sm" onClick={check} loading={test === 'testing'}>{t('fields.testDevice')}</Button>
          {test && test !== 'testing' && (test.error
            ? <span className="text-sm text-danger">{test.error}</span>
            : (
              <span className="flex flex-wrap items-center gap-2 text-sm text-leaf">
                <CheckCircle2 className="size-4" aria-hidden />{t('fields.deviceOk')}
                {Object.entries(test.reading || {}).slice(0, 4).map(([k, v]) => (
                  <span key={k} className="rounded-full bg-sage px-2.5 py-0.5 text-xs text-ink">{t.has(`soilFields.${k}`) ? t(`soilFields.${k}`) : k}: {v}</span>
                ))}
              </span>
            ))}
          {test === 'testing' && <Loader2 className="size-4 animate-spin text-faint" aria-hidden />}
        </div>
      )}
    </div>
  );
}
