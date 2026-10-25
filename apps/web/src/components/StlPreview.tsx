import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { downloadUrl } from "../api";

/** ASSET-003 (SIMPLIFY): basic Three.js STL preview — fetch the asset bytes
 *  through a short-lived presigned URL and render the mesh in a fixed-size
 *  canvas. No LOD/decimation (P1); large meshes may be slow — that limit is
 *  documented, not hidden.
 */
export default function StlPreview({ assetId }: { assetId: string }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let disposed = false;
    let renderer: THREE.WebGLRenderer | null = null;
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
        const center = new THREE.Vector3();
        bb.getCenter(center);
        geo.center();

        const w = mountRef.current.clientWidth || 280;
        const h = 200;
        renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(w, h);
        mountRef.current.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf4f4f4);
        const cam = new THREE.PerspectiveCamera(45, w / h, 0.1, 5000);
        const radius = Math.max(size.x, size.y, size.z) || 1;
        cam.position.set(radius * 1.2, radius * 0.8, radius * 1.5);
        cam.lookAt(0, 0, 0);
        scene.add(new THREE.AmbientLight(0xffffff, 0.9));
        const dir = new THREE.DirectionalLight(0xffffff, 0.8);
        dir.position.set(1, 1, 1);
        scene.add(dir);
        const mesh = new THREE.Mesh(
          geo,
          new THREE.MeshPhongMaterial({ color: 0x7fa3c0 }));
        scene.add(mesh);

        const animate = () => {
          if (disposed) return;
          mesh.rotation.y += 0.01;
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
      renderer?.dispose();
      if (renderer?.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
    };
  }, [assetId]);

  return (
    <div aria-label="stl-preview">
      {loading && !err && <p>Loading preview…</p>}
      {err && <p role="alert" style={{ color: "crimson" }}>Preview failed: {err}</p>}
      <div ref={mountRef} />
    </div>
  );
}
