'use client';

import { Component, type ErrorInfo, type ReactNode, useEffect, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Sphere, MeshDistortMaterial } from '@react-three/drei';
import * as THREE from 'three';

function StaticBackdrop() {
  return (
    <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(79,70,229,0.22),transparent_34%),radial-gradient(circle_at_30%_70%,rgba(14,165,233,0.16),transparent_30%),radial-gradient(circle_at_70%_70%,rgba(244,114,182,0.12),transparent_26%)]" />
      <div className="absolute inset-0 opacity-25 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:44px_44px]" />
    </div>
  );
}

class SceneErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // The landing scene is decorative. If WebGL fails, we quietly fall back.
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }

    return this.props.children;
  }
}

function AnimatedSphere() {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!meshRef.current) {
      return;
    }

    meshRef.current.rotation.y = state.clock.elapsedTime * 0.16;
    meshRef.current.rotation.z = state.clock.elapsedTime * 0.08;
  });

  return (
    <Sphere args={[1, 64, 64]} scale={1.45} ref={meshRef}>
      <MeshDistortMaterial
        color="#4f46e5"
        distort={0.3}
        speed={1.4}
        roughness={0.78}
        metalness={0.12}
        transparent
        opacity={0.7}
        wireframe
      />
    </Sphere>
  );
}

export default function NeuralCoreBackground() {
  const [shouldRenderScene, setShouldRenderScene] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const hasWebGL = typeof window.WebGLRenderingContext !== 'undefined';
    setShouldRenderScene(hasWebGL && !reducedMotion);
  }, []);

  if (!shouldRenderScene) {
    return <StaticBackdrop />;
  }

  return (
    <div className="absolute inset-0 z-0 opacity-30 pointer-events-none mix-blend-screen">
      <SceneErrorBoundary fallback={<StaticBackdrop />}>
        <Canvas
          dpr={[1, 1.5]}
          gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
          camera={{ position: [0, 0, 5], fov: 45 }}
          onCreated={({ gl }) => {
            gl.setClearColor(new THREE.Color('#000000'), 0);
          }}
        >
          <ambientLight intensity={0.55} />
          <directionalLight position={[8, 8, 5]} intensity={1} />
          <AnimatedSphere />
        </Canvas>
      </SceneErrorBoundary>
    </div>
  );
}
