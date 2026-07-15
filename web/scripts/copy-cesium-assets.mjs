import { copyFileSync, cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const cesiumBuild = join(root, "node_modules", "cesium", "Build", "Cesium");
const output = join(root, "public", "cesium");
const assetDirs = ["Assets", "ThirdParty", "Widgets", "Workers"];

mkdirSync(output, { recursive: true });

for (const dir of assetDirs) {
  const target = join(output, dir);
  rmSync(target, { recursive: true, force: true });
  cpSync(join(cesiumBuild, dir), target, { recursive: true });
}

copyFileSync(join(cesiumBuild, "Cesium.js"), join(output, "Cesium.js"));
