import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { downloadUrl } from "../api";

/** ASSET-003 (SIMPLIFY): Three.js STL preview — fetch the asset bytes
 *  through a short-lived presigned URL and render the mesh with
 *  user-controlled OrbitControls (orbit / pan / zoom). No LOD/decimation
 *  (P1); large meshes may be slow — that limit is documented, not hidden.
 */
export default function StlPreview({ assetId }: { assetId: string }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const camRef = useRef<THREE.PerspectiveCamera | null>(null);
  const homeRef = useRef<THREE.Vector3 | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  function resetView() {
    const cam = camRef.current, home = homeRef.current;
    if (!cam || !home) return;
    cam.position.copy(home);
    controlsRef.current?.target.set(0, 0, 0);
    controlsRef.current?.update();
  }

  useEffect(() => {
    let disposed = false;
    let renderer: THREE.WebGLRenderer | null = null;
    let controls: OrbitControls | null = null;
    let frame = 0;

    (async () => {
      try {
        const url = await downloadUrl(assetId);
        const buf = await (await fetch(url)).arrayBuffer();
        if (disposed || !mountRef.current) return;

        const geo = new STLLoader().parse(buf);
        geo.computeBoundingBox();
        const bb = geo.boundingBox!;
        const size = new THREE.Vector3();
        bb.getSize(size);
        geo.center();

        const w = mountRef.current.clientWidth || 280;
        const h = Math.min(340, Math.max(200, Math.round(w * 0.5)));
        renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(w, h);
        mountRef.current.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x10161c);
        const cam = new THREE.PerspectiveCamera(45, w / h, 0.1, 5000);
        const radius = Math.max(size.x, size.y, size.z) || 1;
        cam.position.set(radius * 1.2, radius * 0.8, radius * 1.5);
        cam.lookAt(0, 0, 0);
        camRef.current = cam;
        homeRef.current = cam.position.clone();
        scene.add(new THREE.AmbientLight(0xffffff, 0.9));
        const dir = new THREE.DirectionalLight(0xffffff, 0.8);
        dir.position.set(1, 1, 1);
        scene.add(dir);
        const mesh = new THREE.Mesh(
          geo,
          new THREE.MeshPhongMaterial({ color: 0x7fa3c0 }));
        scene.add(mesh);

        controls = new OrbitControls(cam, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controlsRef.current = controls;

        const animate = () => {
          if (disposed) return;
          controls!.update();
          renderer!.render(scene, cam);
          frame = requestAnimationFrame(animate);
        };
        animate();
        setLoading(false);
      } catch (e) {
        if (!disposed) {
          setErr(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      }
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      controls?.dispose();
      controlsRef.current = null;
      renderer?.dispose();
      if (renderer?.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
    };
  }, [assetId]);

  return (
    <div aria-label="stl-preview">
      {loading && !err && <p className="empty">Loading preview…</p>}
      {err && <p role="alert" className="alert">Preview failed: {err}</p>}
      <div ref={mountRef} className="stl-box" />
      {!loading && !err && (
        <div className="row" style={{ marginTop: 4 }}>
          <span className="stl-hint">
            Drag to orbit · scroll to zoom · right-drag to pan
          </span>
          <button type="button" className="small" onClick={resetView}>
            Reset view
          </button>
        </div>
      )}
    </div>
  );
}
