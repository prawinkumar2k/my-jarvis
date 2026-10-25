import * as THREE from '../../vendor/three.module.min.js';

/**
 * Arc Reactor renderer v3 (Three.js).
 *
 * Every visual parameter eases toward a per-state profile, so state changes
 * blend instead of snapping, and motion is time-based (same speed at any
 * refresh rate). States come from three sources and are combined by priority:
 * speaking > command state (processing/confirmation/error/success) > voice
 * mode (listening) > idle/offline.
 */

const PROFILES = Object.freeze({
    idle:         { color: 0x00e5ff, spin: 0.25, ring: 0.6, breathe: 0.035, freq: 0.9, glow: 0.55, swirl: 0.06, ripple: 0,    jitter: 0 },
    listening:    { color: 0x00ff9c, spin: 0.45, ring: 1.3, breathe: 0.06,  freq: 1.8, glow: 0.8,  swirl: 0.12, ripple: 0.9,  jitter: 0 },
    transcribing: { color: 0x33c4ff, spin: 0.7,  ring: 1.6, breathe: 0.05,  freq: 2.4, glow: 0.75, swirl: 0.2,  ripple: 0,    jitter: 0 },
    processing:   { color: 0xffc400, spin: 1.6,  ring: 3.2, breathe: 0.04,  freq: 3.5, glow: 0.85, swirl: 0.55, ripple: 0,    jitter: 0 },
    speaking:     { color: 0x7af7ff, spin: 0.5,  ring: 1.0, breathe: 0.0,   freq: 0,   glow: 1.0,  swirl: 0.15, ripple: 0,    jitter: 0 },
    confirmation: { color: 0xff9d00, spin: 0.3,  ring: 0.5, breathe: 0.08,  freq: 3.0, glow: 0.9,  swirl: 0.05, ripple: 1.6,  jitter: 0 },
    success:      { color: 0x00ffb3, spin: 0.5,  ring: 1.2, breathe: 0.05,  freq: 1.4, glow: 0.95, swirl: 0.1,  ripple: 0,    jitter: 0 },
    error:        { color: 0xff3366, spin: 0.2,  ring: 0.4, breathe: 0.03,  freq: 6.0, glow: 0.8,  swirl: 0.02, ripple: 0,    jitter: 0.06 },
    offline:      { color: 0x6c7a89, spin: 0.08, ring: 0.2, breathe: 0.015, freq: 0.5, glow: 0.25, swirl: 0.02, ripple: 0,    jitter: 0 },
});

const COMMAND_PRIORITY_STATES = new Set(['processing', 'confirmation', 'error', 'success', 'offline', 'transcribing']);
const EASE_PER_SECOND = 4.5;
const PARTICLE_COUNT = 700;
const RIPPLE_POOL = 6;

function radialTexture() {
    const size = 128;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.25, 'rgba(255,255,255,0.55)');
    g.addColorStop(0.6, 'rgba(255,255,255,0.12)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    return new THREE.CanvasTexture(canvas);
}

export class ArcReactor {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;

        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({
            canvas: this.canvas,
            alpha: true,
            antialias: true,
        });

        this.reducedMotion = false;
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
            this.reducedMotion = Boolean(mq.matches);
            mq.addEventListener('change', (e) => {
                this.reducedMotion = Boolean(e.matches);
            });
        }

        this.commandState = 'idle';
        this.voiceMode = 'idle';
        this.speaking = false;
        this.effectiveState = 'idle';
        this.params = { ...PROFILES.idle };
        this.color = new THREE.Color(PROFILES.idle.color);
        this.targetColor = new THREE.Color(PROFILES.idle.color);
        this.pulse = 0;
        this.rippleClock = 0;
        this.elapsed = 0;
        this.frameId = 0;
        this.clock = new THREE.Clock();

        this.init();
        this.animate();
    }

    init() {
        this.resize();
        this.camera.position.z = 6.0;
        this.disposables = [];
        const track = (obj) => {
            this.disposables.push(obj);
            return obj;
        };
        const glowTexture = track(radialTexture());

        // Halo behind everything (additive glow).
        this.halo = new THREE.Sprite(track(new THREE.SpriteMaterial({
            map: glowTexture,
            color: this.color,
            transparent: true,
            opacity: 0.5,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        })));
        this.halo.scale.set(7, 7, 1);
        this.scene.add(this.halo);

        // Core: wireframe shell + soft inner light.
        this.core = new THREE.Mesh(
            track(new THREE.IcosahedronGeometry(1.15, 3)),
            track(new THREE.MeshBasicMaterial({ color: this.color, wireframe: true, transparent: true, opacity: 0.85 })),
        );
        this.scene.add(this.core);
        this.innerGlow = new THREE.Sprite(track(new THREE.SpriteMaterial({
            map: glowTexture,
            color: this.color,
            transparent: true,
            opacity: 0.9,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        })));
        this.innerGlow.scale.set(2.6, 2.6, 1);
        this.scene.add(this.innerGlow);

        // Containment rings on different axes.
        this.rings = [];
        const ringConfigs = [
            { r: 1.8, w: 0.035, speed: 0.55, tilt: [1.2, 0.3] },
            { r: 2.1, w: 0.022, speed: -0.8, tilt: [0.4, 1.1] },
            { r: 2.4, w: 0.014, speed: 0.35, tilt: [1.9, -0.6] },
        ];
        ringConfigs.forEach((conf) => {
            const mesh = new THREE.Mesh(
                track(new THREE.TorusGeometry(conf.r, conf.w, 12, 160)),
                track(new THREE.MeshBasicMaterial({
                    color: this.color,
                    transparent: true,
                    opacity: 0.55,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false,
                })),
            );
            mesh.rotation.set(conf.tilt[0], conf.tilt[1], 0);
            this.scene.add(mesh);
            this.rings.push({ mesh, speed: conf.speed });
        });

        // Particle shell around the core.
        const positions = new Float32Array(PARTICLE_COUNT * 3);
        this.particleSeeds = new Float32Array(PARTICLE_COUNT * 3); // radius, theta, phi
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const radius = 2.7 + Math.random() * 1.6;
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            this.particleSeeds.set([radius, theta, phi], i * 3);
        }
        const partGeom = track(new THREE.BufferGeometry());
        partGeom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        this.particles = new THREE.Points(partGeom, track(new THREE.PointsMaterial({
            color: this.color,
            size: 0.06,
            map: glowTexture,
            transparent: true,
            opacity: 0.7,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        })));
        this.scene.add(this.particles);
        this.updateParticles(0);

        // Shockwave / ripple pool.
        const rippleGeom = track(new THREE.RingGeometry(0.985, 1.0, 128));
        this.ripples = [];
        for (let i = 0; i < RIPPLE_POOL; i++) {
            const mesh = new THREE.Mesh(rippleGeom, track(new THREE.MeshBasicMaterial({
                color: this.color,
                transparent: true,
                opacity: 0,
                blending: THREE.AdditiveBlending,
                depthWrite: false,
                side: THREE.DoubleSide,
            })));
            mesh.visible = false;
            this.scene.add(mesh);
            this.ripples.push({ mesh, age: 1, life: 1, strength: 0 });
        }
    }

    resize() {
        if (!this.canvas || !this.renderer || !this.camera) return false;
        const size = Math.max(96, Math.round(this.canvas.clientWidth || 300));
        this.camera.aspect = 1;
        this.camera.updateProjectionMatrix();
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        this.renderer.setSize(size, size, false);
        return true;
    }

    /** Command pipeline state: idle, processing, confirmation, success, error, offline. */
    setState(state) {
        this.commandState = PROFILES[state] ? state : 'idle';
        this.refreshState();
    }

    /** Voice mode from main.js: idle, passive, active (listening), processing, transition. */
    setVoiceMode(mode) {
        this.voiceMode = String(mode || 'idle');
        this.refreshState();
    }

    setSpeaking(active) {
        this.speaking = Boolean(active);
        this.refreshState();
    }

    refreshState() {
        let next = 'idle';
        if (this.speaking) next = 'speaking';
        else if (COMMAND_PRIORITY_STATES.has(this.commandState)) next = this.commandState;
        else if (this.voiceMode === 'active') next = 'listening';
        else if (this.voiceMode === 'processing') next = 'processing';
        else next = this.commandState;
        if (next === this.effectiveState) return;
        this.effectiveState = next;
        this.targetColor.setHex(PROFILES[next].color);
        if (next === 'success' || next === 'error') this.triggerPulse(next === 'success' ? 0.9 : 0.7);
        if (this.reducedMotion) {
            Object.assign(this.params, PROFILES[next]);
            this.color.copy(this.targetColor);
            this.applyColor();
            this.renderOnce();
        }
    }

    /** Expanding shockwave plus a short core kick. strength 0..1. */
    triggerPulse(strength = 1) {
        const s = Math.max(0, Math.min(1, Number(strength) || 0));
        this.pulse = Math.max(this.pulse, s);
        if (this.reducedMotion || !this.ripples) return;
        const slot = this.ripples.reduce((a, b) => (b.age / b.life > a.age / a.life ? b : a));
        slot.age = 0;
        slot.life = 1.1 + s * 0.5;
        slot.strength = s;
        slot.mesh.visible = true;
    }

    applyColor() {
        const c = this.color;
        this.core.material.color.copy(c);
        this.innerGlow.material.color.copy(c);
        this.halo.material.color.copy(c);
        this.particles.material.color.copy(c);
        this.rings.forEach((r) => r.mesh.material.color.copy(c));
        this.ripples.forEach((r) => r.mesh.material.color.copy(c));
    }

    updateParticles(dt) {
        const attr = this.particles.geometry.getAttribute('position');
        const arr = attr.array;
        const swirl = this.params.swirl;
        const inward = this.effectiveState === 'processing' ? 0.18 : 0;
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const o = i * 3;
            let radius = this.particleSeeds[o];
            let theta = this.particleSeeds[o + 1];
            const phi = this.particleSeeds[o + 2];
            theta += dt * swirl * (1 + (i % 7) * 0.08);
            radius -= dt * inward * (0.5 + (i % 5) * 0.2);
            if (radius < 1.6) radius = 4.2;
            if (!inward && radius < 2.7) radius += dt * 0.6;
            this.particleSeeds[o] = radius;
            this.particleSeeds[o + 1] = theta;
            const sinPhi = Math.sin(phi);
            arr[o] = radius * sinPhi * Math.cos(theta);
            arr[o + 1] = radius * Math.cos(phi);
            arr[o + 2] = radius * sinPhi * Math.sin(theta);
        }
        attr.needsUpdate = true;
    }

    renderOnce() {
        if (this.renderer) this.renderer.render(this.scene, this.camera);
    }

    animate() {
        this.frameId = requestAnimationFrame(() => this.animate());
        if (typeof document !== 'undefined' && document.hidden) {
            this.clock.getDelta();
            return;
        }
        const dt = Math.min(this.clock.getDelta(), 0.1);
        if (this.reducedMotion) {
            this.renderOnce();
            return;
        }
        this.elapsed += dt;
        const t = this.elapsed;

        // Ease parameters and color toward the active profile.
        const target = PROFILES[this.effectiveState] || PROFILES.idle;
        const k = 1 - Math.exp(-EASE_PER_SECOND * dt);
        for (const key of Object.keys(this.params)) {
            if (key !== 'color') this.params[key] += (target[key] - this.params[key]) * k;
        }
        this.color.lerp(this.targetColor, k);
        this.applyColor();
        this.pulse = Math.max(0, this.pulse - dt * 1.8);

        const p = this.params;
        let scale = 1 + Math.sin(t * Math.PI * p.freq) * p.breathe;
        if (this.effectiveState === 'speaking') {
            // Voice-like envelope: a few incommensurate sines.
            const env = Math.abs(Math.sin(t * 9.1) * 0.5 + Math.sin(t * 13.7) * 0.3 + Math.sin(t * 5.3) * 0.2);
            scale = 1 + env * 0.11;
        }
        if (this.effectiveState === 'confirmation') {
            p.glow = target.glow * (0.65 + 0.35 * (0.5 + 0.5 * Math.sin(t * 6)));
        }
        scale += this.pulse * 0.18;

        this.core.rotation.y += dt * p.spin;
        this.core.rotation.z += dt * p.spin * 0.4;
        this.core.scale.setScalar(scale);
        const jitter = p.jitter;
        this.core.position.set(jitter ? (Math.random() - 0.5) * jitter : 0, jitter ? (Math.random() - 0.5) * jitter : 0, 0);

        this.innerGlow.scale.setScalar(2.4 * scale + this.pulse * 0.8);
        this.innerGlow.material.opacity = 0.45 + p.glow * 0.5;
        this.halo.material.opacity = 0.18 + p.glow * 0.42 + this.pulse * 0.25;
        this.halo.scale.setScalar(6.2 + p.glow * 1.6 + this.pulse * 1.5);

        this.rings.forEach((r, i) => {
            r.mesh.rotation.x += dt * r.speed * p.ring;
            r.mesh.rotation.y += dt * r.speed * p.ring * 0.6;
            r.mesh.material.opacity = 0.35 + p.glow * 0.35 + Math.sin(t * 2 + i) * 0.05;
        });

        this.updateParticles(dt);
        this.particles.rotation.y -= dt * 0.04;
        this.particles.material.opacity = 0.35 + p.glow * 0.45;

        // Listening / confirmation emit ripples on a rhythm.
        if (p.ripple > 0.05 && target.ripple > 0) {
            this.rippleClock += dt;
            if (this.rippleClock >= target.ripple) {
                this.rippleClock = 0;
                this.triggerPulse(0.35);
                this.pulse = Math.min(this.pulse, 0.15);
            }
        } else {
            this.rippleClock = 0;
        }
        this.ripples.forEach((r) => {
            if (!r.mesh.visible) return;
            r.age += dt;
            const life = r.age / r.life;
            if (life >= 1) {
                r.mesh.visible = false;
                r.mesh.material.opacity = 0;
                return;
            }
            const eased = 1 - Math.pow(1 - life, 3);
            r.mesh.scale.setScalar(1.3 + eased * (2.2 + r.strength * 1.6));
            r.mesh.material.opacity = (1 - life) * (0.35 + r.strength * 0.45);
        });

        this.renderer.render(this.scene, this.camera);
    }

    dispose() {
        if (this.frameId) cancelAnimationFrame(this.frameId);
        this.frameId = 0;
        (this.disposables || []).forEach((obj) => {
            if (obj && typeof obj.dispose === 'function') obj.dispose();
        });
        this.disposables = [];
        if (this.renderer) this.renderer.dispose();
    }
}
