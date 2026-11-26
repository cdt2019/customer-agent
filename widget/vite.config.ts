import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 打成一个能用 <script> 引入的文件，样式内联进脚本，挂在 Shadow DOM 里
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    lib: { entry: "src/main.tsx", name: "CustomerAgent", formats: ["iife"], fileName: () => "widget.js" },
    cssCodeSplit: false,
  },
});
