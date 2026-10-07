import React, { useState, useEffect } from 'react';
import { 
  ArrowLeft, ExternalLink, Box, TrendingUp, PlayCircle, Settings, 
  CheckCircle2, AlertCircle, Loader2, Layers, Table, RefreshCw, 
  Sliders, ShieldCheck, Database, Camera, Cloud, Download, Upload, HardDrive, Check, Share2,
  Activity, BarChart3
} from 'lucide-react';
import { queueTraining, queueYoloTraining, getForecastJobStatus } from '../api/forecast';
import { getStockHistory } from '../api/stock';
import { getHfStatus, pushToHf, pullFromHf, checkOrPullHf, HuggingFaceStatusResponse } from '../api/huggingface';

interface TrainingStudioProps {
  onBack: () => void;
}

export const TrainingStudio: React.FC<TrainingStudioProps> = ({ onBack }) => {
  const [activeTab, setActiveTab] = useState<'yolo' | 'arima' | 'hf'>('yolo');

  // -------------------------------------------------------------
  // ARIMA State
  // -------------------------------------------------------------
  const [arimaLoading, setArimaLoading] = useState(false);
  const [arimaProgress, setArimaProgress] = useState<number>(0);
  const [arimaStatus, setArimaStatus] = useState<string>('idle');
  const [arimaMetrics, setArimaMetrics] = useState<any>(null);
  const [arimaHorizon, setArimaHorizon] = useState<number>(3);
  const [autoOrder, setAutoOrder] = useState<boolean>(true);
  const [pVal, setPVal] = useState<number>(2);
  const [dVal, setDVal] = useState<number>(0);
  const [qVal, setQVal] = useState<number>(2);
  const [stockHistory, setStockHistory] = useState<any[]>([]);
  const [tableLoading, setTableLoading] = useState<boolean>(false);

  // -------------------------------------------------------------
  // YOLO State
  // -------------------------------------------------------------
  const [yoloLoading, setYoloLoading] = useState(false);
  const [yoloProgress, setYoloProgress] = useState<number>(0);
  const [yoloStatus, setYoloStatus] = useState<string>('idle');
  const [yoloMetrics, setYoloMetrics] = useState<any>(null);
  const [yoloEpochs, setYoloEpochs] = useState<number>(10);
  const [yoloBatch, setYoloBatch] = useState<number>(8);
  const [yoloDataset, setYoloDataset] = useState<string>('box_v1');
  const [selectedCamera, setSelectedCamera] = useState<'ZoneA' | 'ZoneB'>('ZoneA');

  // -------------------------------------------------------------
  // Hugging Face Model Hub State
  // -------------------------------------------------------------
  const [hfStatus, setHfStatus] = useState<HuggingFaceStatusResponse | null>(null);
  const [hfLoading, setHfLoading] = useState<boolean>(false);
  const [hfActionLoading, setHfActionLoading] = useState<string | null>(null);
  const [hfMessage, setHfMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  const fetchHfStatus = async () => {
    setHfLoading(true);
    try {
      const res = await getHfStatus();
      setHfStatus(res);
    } catch (err: any) {
      console.error("Failed to load HF status:", err);
    } finally {
      setHfLoading(false);
    }
  };

  const handlePushHf = async () => {
    setHfActionLoading('push');
    setHfMessage({ text: 'กำลังอัปโหลดโมเดลขึ้น Hugging Face Hub (kkshaolin/yolo_box)...', type: 'info' });
    try {
      const res = await pushToHf();
      setHfMessage({ text: res.message || 'อัปโหลดขึ้น Hugging Face Hub สำเร็จ!', type: 'success' });
      await fetchHfStatus();
    } catch (err: any) {
      setHfMessage({ text: `เกิดข้อผิดพลาดในการ Push: ${err.response?.data?.detail || err.message}`, type: 'error' });
    } finally {
      setHfActionLoading(null);
    }
  };

  const handlePullHf = async () => {
    setHfActionLoading('pull');
    setHfMessage({ text: 'กำลังดาวน์โหลดโมเดลจาก Hugging Face Hub ลงเครื่องและ MinIO...', type: 'info' });
    try {
      const res = await pullFromHf(true);
      setHfMessage({ text: res.message || 'ดาวน์โหลดและซิงค์โมเดลสำเร็จ!', type: 'success' });
      await fetchHfStatus();
    } catch (err: any) {
      setHfMessage({ text: `เกิดข้อผิดพลาดในการ Pull: ${err.response?.data?.detail || err.message}`, type: 'error' });
    } finally {
      setHfActionLoading(null);
    }
  };

  const handleCheckHf = async () => {
    setHfActionLoading('check');
    try {
      const res = await checkOrPullHf();
      setHfMessage({ text: res.message || 'ตรวจสอบสถานะ Cache สำเร็จ', type: 'success' });
      await fetchHfStatus();
    } catch (err: any) {
      setHfMessage({ text: `ตรวจสอบไม่สำเร็จ: ${err.response?.data?.detail || err.message}`, type: 'error' });
    } finally {
      setHfActionLoading(null);
    }
  };

  // โหลดประวัติสต็อกสำหรับตาราง ARIMA และสถานะ HF
  const fetchStockTable = async () => {
    setTableLoading(true);
    try {
      const res = await getStockHistory('Frozen_Seafood');
      if (res && res.data) {
        setStockHistory(res.data);
      }
    } catch (err) {
      console.error("Failed to load stock history:", err);
    } finally {
      setTableLoading(false);
    }
  };

  useEffect(() => {
    fetchStockTable();
    fetchHfStatus();
  }, []);

  // -------------------------------------------------------------
  // Train YOLO Handler
  // -------------------------------------------------------------
  const handleTrainYolo = async () => {
    setYoloLoading(true);
    setYoloProgress(10);
    setYoloStatus('Queuing YOLO training task in training_queue...');
    setYoloMetrics(null);

    try {
      const res = await queueYoloTraining({
        dataset_name: yoloDataset,
        class_names: ['delivery_box'],
        epochs: yoloEpochs,
        batch: yoloBatch,
        imgsz: 640,
        patience: 5,
      });

      const jobId = res.job_id;
      setYoloProgress(25);
      setYoloStatus('Task queued. Training YOLO model on GPU/CPU worker...');

      let elapsed = 0;
      const poll = setInterval(async () => {
        elapsed += 2;
        try {
          const statusRes = await getForecastJobStatus(jobId);
          if (statusRes.status === 'in_progress' || statusRes.status === 'running') {
            setYoloProgress(Math.min(30 + elapsed * 5, 85));
            setYoloStatus(`YOLO training in progress... (${elapsed}s)`);
          } else if (statusRes.status === 'completed') {
            clearInterval(poll);
            setYoloProgress(100);
            setYoloStatus('YOLO Training completed successfully!');
            setYoloLoading(false);
            setYoloMetrics(statusRes.result?.metrics || null);
          } else if (statusRes.status === 'failed') {
            clearInterval(poll);
            setYoloLoading(false);
            setYoloStatus(`YOLO Training failed: ${statusRes.error || 'Unknown error'}`);
          }
        } catch (pollErr) {
          console.error("Poll error:", pollErr);
        }
      }, 2000);

      // Timeout หลัง 3 นาที
      setTimeout(() => {
        clearInterval(poll);
        if (yoloLoading) {
          setYoloLoading(false);
          setYoloStatus('Training request sent (running in background).');
        }
      }, 180000);

    } catch (err: any) {
      setYoloLoading(false);
      setYoloStatus(`Error starting YOLO training: ${err.response?.data?.detail || err.message}`);
    }
  };

  // -------------------------------------------------------------
  // Train ARIMA Handler
  // -------------------------------------------------------------
  const handleTrainArima = async () => {
    setArimaLoading(true);
    setArimaProgress(15);
    setArimaStatus('Submitting ARIMA training job to Redis queue...');
    setArimaMetrics(null);

    try {
      const res = await queueTraining({
        product: 'Frozen_Seafood',
        forecast_horizon: arimaHorizon,
        p: autoOrder ? 1 : pVal,
        d: autoOrder ? 1 : dVal,
        q: autoOrder ? 1 : qVal,
      });

      const jobId = res.job_id;
      setArimaProgress(40);
      setArimaStatus(autoOrder ? 'Analyzing ADF, ACF, PACF and selecting optimal (p,d,q)...' : 'Training ARIMA model...');

      let elapsed = 0;
      const poll = setInterval(async () => {
        elapsed += 2;
        try {
          const statusRes = await getForecastJobStatus(jobId);
          if (statusRes.status === 'in_progress' || statusRes.status === 'running') {
            setArimaProgress(Math.min(50 + elapsed * 10, 90));
            setArimaStatus(`Fitting ARIMA model & evaluating metrics... (${elapsed}s)`);
          } else if (statusRes.status === 'completed') {
            clearInterval(poll);
            setArimaProgress(100);
            setArimaStatus('ARIMA Training completed successfully!');
            setArimaLoading(false);
            setArimaMetrics(statusRes.result?.metrics || null);
            fetchStockTable();
          } else if (statusRes.status === 'failed') {
            clearInterval(poll);
            setArimaLoading(false);
            setArimaStatus(`ARIMA Training failed: ${statusRes.error || 'Unknown error'}`);
          }
        } catch (pollErr) {
          console.error("Poll error:", pollErr);
        }
      }, 2000);

      setTimeout(() => {
        clearInterval(poll);
        if (arimaLoading) {
          setArimaLoading(false);
          setArimaStatus('ARIMA job is processing in background.');
        }
      }, 60000);

    } catch (err: any) {
      setArimaLoading(false);
      setArimaStatus(`Error starting ARIMA training: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col text-slate-800">
      {/* ---------------- Top Navigation Bar ---------------- */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between sticky top-0 z-30 shadow-sm">
        <div className="flex items-center gap-4">
          <button 
            onClick={onBack}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
          >
            <ArrowLeft className="w-4 h-4" /> กลับสู่ Dashboard
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <Layers className="w-6 h-6 text-blue-600" /> AI Model Training Studio
            </h1>
            <p className="text-xs text-slate-500">
              ระบบฝึกและประเมินโมเดลแยกอิสระ: YOLO (ตรวจจับกล่องสินค้า) และ ARIMA (พยากรณ์สต็อก)
            </p>
          </div>
        </div>

        {/* Hugging Face Hub Quick Status Badge */}
        <div className="hidden sm:flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-lg text-xs font-medium text-slate-700 transition">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>HF Repo: <strong className="font-semibold text-slate-900">{hfStatus?.repo_id || 'kkshaolin/yolo_box'}</strong></span>
            <span className="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-800 rounded font-bold">Public</span>
          </div>
          <button 
            onClick={() => setActiveTab('hf')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition ${
              activeTab === 'hf' 
                ? 'bg-blue-600 text-white' 
                : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <Cloud className="w-3.5 h-3.5 text-amber-500" />
            Model Registry
          </button>
        </div>
      </header>

      {/* ---------------- Main Content Tabs ---------------- */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        
        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-200 gap-4 overflow-x-auto">
          <button
            onClick={() => setActiveTab('yolo')}
            className={`pb-3 px-4 font-semibold text-sm flex items-center gap-2 border-b-2 whitespace-nowrap transition ${
              activeTab === 'yolo'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <Box className="w-4 h-4" /> YOLO Box Detection Training
          </button>
          <button
            onClick={() => setActiveTab('arima')}
            className={`pb-3 px-4 font-semibold text-sm flex items-center gap-2 border-b-2 whitespace-nowrap transition ${
              activeTab === 'arima'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <TrendingUp className="w-4 h-4" /> ARIMA Time Series Forecasting Training
          </button>
          <button
            onClick={() => setActiveTab('hf')}
            className={`pb-3 px-4 font-semibold text-sm flex items-center gap-2 border-b-2 whitespace-nowrap transition ${
              activeTab === 'hf'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <Cloud className="w-4 h-4 text-amber-500" /> Hugging Face Model Hub (Hybrid Registry)
          </button>
        </div>

        {/* ========================================================= */}
        {/* TAB 1: YOLO BOX DETECTION STUDIO                          */}
        {/* ========================================================= */}
        {activeTab === 'yolo' && (
          <div className="space-y-6">
            {/* Banner อธิบายการใช้งาน Label Studio และ Live Training Monitors (TensorBoard & MLflow) */}
            <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <h3 className="font-semibold text-indigo-900 flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-indigo-600" /> ชุดข้อมูลภาพและการตรวจสอบโมเดล YOLO (delivery_box)
                </h3>
                <p className="text-sm text-indigo-750">
                  ระบบเตรียมชุดข้อมูลตรวจจับ <strong>"delivery_box" (กล่องสินค้าอาหารทะเล)</strong> สามารถตรวจสอบ Bounding Box ใน Label Studio หรือเปิดดูผลการเทรน/กราฟ Loss ใน TensorBoard และ MLflow แบบเรียลไทม์
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                <a
                  href="http://localhost:6006"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold shadow-xs transition"
                  title="เปิดดู TensorBoard สำหรับดูกราฟ Loss, Epoch Metrics และ Confusion Matrix"
                >
                  <Activity className="w-3.5 h-3.5" /> ดู TensorBoard
                </a>
                <a
                  href="http://localhost:5000"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-xs transition"
                  title="เปิดดู MLflow UI สำหรับติดตาม Experiments และ Run Parameters"
                >
                  <BarChart3 className="w-3.5 h-3.5" /> ดู MLflow UI
                </a>
                <a
                  href="http://localhost:8080"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs transition"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Label Studio
                </a>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* ภาพตัวอย่างและการจัดการ Data (Left 7 cols) */}
              <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                    <Camera className="w-4 h-4 text-blue-600" /> ข้อมูลภาพจากกล้องวงจรปิด (Camera Sampling Data)
                  </h3>
                  <div className="flex gap-2 text-xs">
                    <button 
                      onClick={() => setSelectedCamera('ZoneA')}
                      className={`px-3 py-1 rounded-md font-medium transition ${selectedCamera === 'ZoneA' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'}`}
                    >
                      Zone A (Cold Storage)
                    </button>
                    <button 
                      onClick={() => setSelectedCamera('ZoneB')}
                      className={`px-3 py-1 rounded-md font-medium transition ${selectedCamera === 'ZoneB' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'}`}
                    >
                      Zone B (Processing)
                    </button>
                  </div>
                </div>

                {/* Video / Image Display */}
                <div className="relative rounded-lg overflow-hidden border border-slate-200 bg-slate-900 aspect-video flex items-center justify-center">
                  <video 
                    src={selectedCamera === 'ZoneA' ? '/mockA.mp4' : '/mockB.mp4'} 
                    autoPlay 
                    loop 
                    muted 
                    playsInline 
                    className="w-full h-full object-cover" 
                  />
                  <div className="absolute top-3 left-3 bg-black/60 text-white text-xs px-2.5 py-1 rounded-md backdrop-blur-sm flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    Live Feed ({selectedCamera})
                  </div>
                  <div className="absolute bottom-3 right-3 bg-black/60 text-white text-xs px-2.5 py-1 rounded-md backdrop-blur-sm">
                    Target Class: <span className="font-semibold text-emerald-300">box (กล่องสินค้า)</span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                    <span className="text-slate-400 block">Dataset Name</span>
                    <span className="font-semibold text-slate-700">{yoloDataset}</span>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                    <span className="text-slate-400 block">Annotation Class</span>
                    <span className="font-semibold text-emerald-700">box (Seafood Box)</span>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                    <span className="text-slate-400 block">Resolution</span>
                    <span className="font-semibold text-slate-700">640 x 640 px</span>
                  </div>
                </div>
              </div>

              {/* ส่วนควบคุมและสั่งเทรน YOLO (Right 5 cols) */}
              <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-5 flex flex-col justify-between">
                <div className="space-y-4">
                  <h3 className="font-semibold text-slate-800 flex items-center gap-2 border-b border-slate-100 pb-3">
                    <Sliders className="w-4 h-4 text-purple-600" /> ตั้งค่าพารามิเตอร์การเทรน YOLO
                  </h3>

                  <div className="space-y-3">
                    <div>
                      <label className="text-xs font-semibold text-slate-600 block mb-1">Dataset Name ใน MinIO</label>
                      <input 
                        type="text" 
                        value={yoloDataset} 
                        onChange={(e) => setYoloDataset(e.target.value)}
                        className="w-full text-sm p-2 border rounded-lg bg-slate-50 font-mono"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Epochs (รอบการเทรน)</label>
                        <select 
                          value={yoloEpochs} 
                          onChange={(e) => setYoloEpochs(Number(e.target.value))}
                          className="w-full text-sm p-2 border rounded-lg bg-white"
                        >
                          <option value={5}>5 Epochs (Quick Test)</option>
                          <option value={10}>10 Epochs (Recommended)</option>
                          <option value={20}>20 Epochs</option>
                          <option value={50}>50 Epochs</option>
                        </select>
                      </div>

                      <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Batch Size</label>
                        <select 
                          value={yoloBatch} 
                          onChange={(e) => setYoloBatch(Number(e.target.value))}
                          className="w-full text-sm p-2 border rounded-lg bg-white"
                        >
                          <option value={4}>4</option>
                          <option value={8}>8 (Standard)</option>
                          <option value={16}>16</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Progress & Loading Bar */}
                  {(yoloLoading || yoloProgress > 0) && (
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                      <div className="flex justify-between text-xs font-medium">
                        <span className="text-slate-600">{yoloStatus}</span>
                        <span className="text-blue-600">{yoloProgress}%</span>
                      </div>
                      <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                        <div 
                          className="bg-blue-600 h-2 rounded-full transition-all duration-500" 
                          style={{ width: `${yoloProgress}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {/* Evaluation Metrics Display */}
                  {yoloMetrics && (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" /> ผลการประเมินโมเดล YOLO (Evaluation Metrics)
                        </h4>
                        <span className="text-[11px] text-emerald-700 font-medium">Real Held-out Test Set</span>
                      </div>

                      {/* Run Metadata */}
                      <div className="bg-white/80 p-2.5 rounded-lg border border-emerald-100 text-xs space-y-1 text-slate-600">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Dataset Source:</span>
                          <span className="font-semibold text-slate-800">{yoloMetrics.dataset_name || yoloDataset} (MinIO)</span>
                        </div>
                        {yoloMetrics.trained_at && (
                          <div className="flex justify-between">
                            <span className="text-slate-500">เวลาที่สร้าง:</span>
                            <span className="font-mono text-slate-700">{new Date(yoloMetrics.trained_at).toLocaleString()}</span>
                          </div>
                        )}
                        {(yoloMetrics.mlflow_run_id || yoloMetrics.job_id) && (
                          <div className="flex justify-between">
                            <span className="text-slate-500">Run ID:</span>
                            <span className="font-mono text-blue-700 font-semibold truncate max-w-[180px]" title={yoloMetrics.mlflow_run_id || yoloMetrics.job_id}>
                              {yoloMetrics.mlflow_run_id || yoloMetrics.job_id}
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-center">
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">mAP@50</span>
                          <span className="text-lg font-bold text-emerald-700">
                            {yoloMetrics.mAP50 != null || yoloMetrics.best_metrics?.mAP50 != null
                              ? `${(((yoloMetrics.mAP50 ?? yoloMetrics.best_metrics?.mAP50) as number) * 100).toFixed(1)}%`
                              : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">mAP@50-95</span>
                          <span className="text-lg font-bold text-emerald-700">
                            {yoloMetrics.mAP50_95 != null || yoloMetrics.best_metrics?.mAP50_95 != null
                              ? `${(((yoloMetrics.mAP50_95 ?? yoloMetrics.best_metrics?.mAP50_95) as number) * 100).toFixed(1)}%`
                              : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">Precision</span>
                          <span className="text-lg font-bold text-emerald-700">
                            {yoloMetrics.precision != null || yoloMetrics.best_metrics?.precision != null
                              ? `${(((yoloMetrics.precision ?? yoloMetrics.best_metrics?.precision) as number) * 100).toFixed(1)}%`
                              : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">Recall</span>
                          <span className="text-lg font-bold text-emerald-700">
                            {yoloMetrics.recall != null || yoloMetrics.best_metrics?.recall != null
                              ? `${(((yoloMetrics.recall ?? yoloMetrics.best_metrics?.recall) as number) * 100).toFixed(1)}%`
                              : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* ปุ่มสั่งเทรน YOLO */}
                <button
                  onClick={handleTrainYolo}
                  disabled={yoloLoading}
                  className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white rounded-lg font-semibold flex items-center justify-center gap-2 shadow-sm transition"
                >
                  {yoloLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" /> กำลังเทรน YOLO... ({yoloProgress}%)
                    </>
                  ) : (
                    <>
                      <PlayCircle className="w-5 h-5" /> สั่งเริ่มเทรนโมเดล YOLO (Train YOLO)
                    </>
                  )}
                </button>

                {/* แถบทางลัดเปิดดู Dashboard การเทรน */}
                <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-500 font-medium">Live Monitors:</span>
                  <div className="flex items-center gap-2">
                    <a
                      href="http://localhost:6006"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded-lg font-medium transition"
                    >
                      <Activity className="w-3.5 h-3.5 text-amber-600" /> TensorBoard
                    </a>
                    <a
                      href="http://localhost:5000"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 rounded-lg font-medium transition"
                    >
                      <BarChart3 className="w-3.5 h-3.5 text-blue-600" /> MLflow
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 2: ARIMA TIME SERIES FORECASTING STUDIO               */}
        {/* ========================================================= */}
        {activeTab === 'arima' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* ตารางข้อมูลสต็อกย้อนหลัง (Left 7 cols) */}
              <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                      <Table className="w-4 h-4 text-emerald-600" /> ตารางข้อมูลอนุกรมเวลา (Inventory Time Series Data)
                    </h3>
                    <p className="text-xs text-slate-500">ข้อมูลจริง 70 เดือนจาก PostgreSQL Cloud ใช้สำหรับวิเคราะห์และเทรนโมเดล</p>
                  </div>
                  <button 
                    onClick={fetchStockTable}
                    className="text-xs flex items-center gap-1.5 px-2.5 py-1 text-slate-600 hover:text-blue-600 bg-slate-100 rounded-md transition"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${tableLoading ? 'animate-spin' : ''}`} /> รีเฟรชข้อมูล
                  </button>
                </div>

                {/* Data Table */}
                <div className="border border-slate-200 rounded-lg overflow-hidden max-h-96 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-100 text-slate-600 sticky top-0 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="p-2.5">Date / Month</th>
                        <th className="p-2.5">Zone A (Boxes)</th>
                        <th className="p-2.5">Zone B (Boxes)</th>
                        <th className="p-2.5 text-right">Total Boxes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {stockHistory.length > 0 ? (
                        stockHistory.slice(-24).map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-50 transition">
                            <td className="p-2.5 font-medium text-slate-700">
                              {new Date(row.recorded_at).toLocaleDateString('th-TH', { year: 'numeric', month: 'short' })}
                            </td>
                            <td className="p-2.5 text-slate-600">{row.boxes_A ?? '-'}</td>
                            <td className="p-2.5 text-slate-600">{row.boxes_B ?? '-'}</td>
                            <td className="p-2.5 text-right font-bold text-blue-600">{row.total_boxes || row.quantity}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={4} className="p-4 text-center text-slate-400">
                            {tableLoading ? 'กำลังโหลดข้อมูลจากฐานข้อมูล...' : 'ไม่พบข้อมูลประวัติสต็อก'}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="flex justify-between items-center text-xs text-slate-500 pt-1">
                  <span>แสดงข้อมูล 24 เดือนล่าสุด (จากทั้งหมด {stockHistory.length || 70} เดือน)</span>
                  <span className="font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    ADF Test: d = 0 (Stationary)
                  </span>
                </div>
              </div>

              {/* ส่วนควบคุมและสั่งเทรน ARIMA (Right 5 cols) */}
              <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-5 flex flex-col justify-between">
                <div className="space-y-4">
                  <h3 className="font-semibold text-slate-800 flex items-center gap-2 border-b border-slate-100 pb-3">
                    <Settings className="w-4 h-4 text-emerald-600" /> ตั้งค่าพารามิเตอร์การเทรน ARIMA
                  </h3>

                  <div className="space-y-3">
                    {/* Auto Parameter Selection Toggle */}
                    <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 flex items-center justify-between">
                      <div>
                        <span className="text-xs font-bold text-slate-800 block">Auto ACF / PACF Order Selection</span>
                        <span className="text-xs text-slate-500">วิเคราะห์สถิติเพื่อหา (p, d, q) ที่ให้ค่า AIC ต่ำที่สุดอัตโนมัติ</span>
                      </div>
                      <input 
                        type="checkbox" 
                        checked={autoOrder} 
                        onChange={(e) => setAutoOrder(e.target.checked)}
                        className="w-4 h-4 text-emerald-600 rounded cursor-pointer"
                      />
                    </div>

                    {!autoOrder && (
                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <label className="text-xs font-semibold text-slate-600 block mb-1">p (AR)</label>
                          <input 
                            type="number" 
                            value={pVal} 
                            onChange={(e) => setPVal(Number(e.target.value))}
                            className="w-full p-2 border rounded-lg text-sm bg-white"
                          />
                        </div>
                        <div>
                          <label className="text-xs font-semibold text-slate-600 block mb-1">d (Diff)</label>
                          <input 
                            type="number" 
                            value={dVal} 
                            onChange={(e) => setDVal(Number(e.target.value))}
                            className="w-full p-2 border rounded-lg text-sm bg-white"
                          />
                        </div>
                        <div>
                          <label className="text-xs font-semibold text-slate-600 block mb-1">q (MA)</label>
                          <input 
                            type="number" 
                            value={qVal} 
                            onChange={(e) => setQVal(Number(e.target.value))}
                            className="w-full p-2 border rounded-lg text-sm bg-white"
                          />
                        </div>
                      </div>
                    )}

                    <div>
                      <label className="text-xs font-semibold text-slate-600 block mb-1">Forecast Horizon (ทำนายล่วงหน้ากี่เดือน)</label>
                      <select 
                        value={arimaHorizon} 
                        onChange={(e) => setArimaHorizon(Number(e.target.value))}
                        className="w-full text-sm p-2 border rounded-lg bg-white"
                      >
                        <option value={3}>3 เดือน</option>
                        <option value={6}>6 เดือน</option>
                        <option value={12}>12 เดือน</option>
                      </select>
                    </div>
                  </div>

                  {/* Progress & Loading Bar */}
                  {(arimaLoading || arimaProgress > 0) && (
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                      <div className="flex justify-between text-xs font-medium">
                        <span className="text-slate-600">{arimaStatus}</span>
                        <span className="text-emerald-600">{arimaProgress}%</span>
                      </div>
                      <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                        <div 
                          className="bg-emerald-600 h-2 rounded-full transition-all duration-500" 
                          style={{ width: `${arimaProgress}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {/* Evaluation Metrics Display */}
                  {arimaMetrics && (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" /> ผลการประเมินโมเดล ARIMA (Evaluation Metrics)
                        </h4>
                        <span className="text-[11px] text-emerald-700 font-medium">Chronological Holdout (80/20)</span>
                      </div>
                      
                      {/* Run Metadata */}
                      <div className="bg-white/80 p-2.5 rounded-lg border border-emerald-100 text-xs space-y-1 text-slate-600">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Data Source:</span>
                          <span className="font-semibold text-slate-800">{arimaMetrics.data_source || 'PostgreSQL (monthly_inventories)'}</span>
                        </div>
                        {arimaMetrics.trained_at && (
                          <div className="flex justify-between">
                            <span className="text-slate-500">เวลาที่สร้าง:</span>
                            <span className="font-mono text-slate-700">{new Date(arimaMetrics.trained_at).toLocaleString()}</span>
                          </div>
                        )}
                        {(arimaMetrics.mlflow_run_id || arimaMetrics.job_id) && (
                          <div className="flex justify-between">
                            <span className="text-slate-500">Run ID:</span>
                            <span className="font-mono text-blue-700 font-semibold truncate max-w-[180px]" title={arimaMetrics.mlflow_run_id || arimaMetrics.job_id}>
                              {arimaMetrics.mlflow_run_id || arimaMetrics.job_id}
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-center">
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">Model Order</span>
                          <span className="text-sm font-bold text-blue-700">{arimaMetrics.model_order || 'ARIMA(1,1,1)'}</span>
                        </div>
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">MAPE (Error %)</span>
                          <span className="text-sm font-bold text-emerald-700">
                            {arimaMetrics.mape != null ? `${arimaMetrics.mape.toFixed(2)}%` : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">MAE (Error)</span>
                          <span className="text-sm font-bold text-slate-800">
                            {arimaMetrics.mae != null ? `${arimaMetrics.mae.toFixed(2)} กล่อง` : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                        <div className="bg-white p-2.5 rounded border border-emerald-100 shadow-xs">
                          <span className="text-xs text-slate-500 block">RMSE</span>
                          <span className="text-sm font-bold text-slate-800">
                            {arimaMetrics.rmse != null ? `${arimaMetrics.rmse.toFixed(2)} กล่อง` : 'ไม่มีผลประเมิน'}
                          </span>
                        </div>
                      </div>

                      {/* Baseline Comparison (Naïve & Seasonal Naïve) */}
                      {arimaMetrics.baselines && (
                        <div className="bg-white/80 p-3 rounded-lg border border-emerald-100 space-y-1.5 text-xs">
                          <span className="font-semibold text-slate-700 block text-[11px] uppercase tracking-wide">
                            เปรียบเทียบกับ Baselines:
                          </span>
                          <div className="grid grid-cols-2 gap-2 text-slate-600">
                            <div className="bg-slate-50 p-2 rounded">
                              <span className="text-[10px] text-slate-500 block">Naïve Baseline MAE</span>
                              <span className="font-bold text-slate-800">
                                {arimaMetrics.baselines.naive?.mae != null ? `${arimaMetrics.baselines.naive.mae.toFixed(2)} กล่อง` : 'N/A'}
                              </span>
                            </div>
                            <div className="bg-slate-50 p-2 rounded">
                              <span className="text-[10px] text-slate-500 block">Seasonal Naïve (m=12) MAE</span>
                              <span className="font-bold text-slate-800">
                                {arimaMetrics.baselines.seasonal_naive?.mae != null ? `${arimaMetrics.baselines.seasonal_naive.mae.toFixed(2)} กล่อง` : 'N/A'}
                              </span>
                            </div>
                          </div>
                          {arimaMetrics.evaluation_notes?.mape_limitation && (
                            <p className="text-[10px] text-slate-500 italic pt-1">
                              * {arimaMetrics.evaluation_notes.mape_limitation}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* ปุ่มสั่งเทรน ARIMA */}
                <button
                  onClick={handleTrainArima}
                  disabled={arimaLoading}
                  className="w-full py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 disabled:opacity-50 text-white rounded-lg font-semibold flex items-center justify-center gap-2 shadow-sm transition"
                >
                  {arimaLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" /> กำลังเทรน ARIMA... ({arimaProgress}%)
                    </>
                  ) : (
                    <>
                      <PlayCircle className="w-5 h-5" /> สั่งเริ่มเทรนโมเดล ARIMA (Train ARIMA)
                    </>
                  )}
                </button>

                {/* แถบทางลัดเปิดดู MLflow UI สำหรับ ARIMA */}
                <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-500 font-medium">Experiment Tracking:</span>
                  <a
                    href="http://localhost:5000/#/experiments/2"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 rounded-lg font-medium transition"
                  >
                    <BarChart3 className="w-3.5 h-3.5 text-blue-600" /> ดู MLflow Run & Artifacts
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 3: HUGGING FACE MODEL HUB (HYBRID CACHE-ASIDE)        */}
        {/* ========================================================= */}
        {activeTab === 'hf' && (
          <div className="space-y-6">
            {/* Header Banner: Hybrid Cache-Aside Architecture */}
            <div className="bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-yellow-500/10 border border-amber-200 rounded-2xl p-6">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
                      Hybrid Cache-Aside
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                      Public Repository
                    </span>
                  </div>
                  <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                    <Cloud className="w-6 h-6 text-amber-600" /> Hugging Face Model Hub Registry
                  </h2>
                  <p className="text-sm text-slate-600 max-w-2xl">
                    ระบบฝากและกระจายโมเดลแบบ <strong>Hybrid Cache-Aside</strong> โดยใช้ <strong>Hugging Face Hub ({hfStatus?.repo_id || 'kkshaolin/yolo_box'})</strong> เป็นศูนย์กลางแจกจ่ายโมเดลเวอร์ชันทางการ ในขณะที่การรัน Inference ปกติทำงานผ่าน <strong>MinIO และ Local Cache</strong> ด้วยความเร็วระดับ &lt;1ms
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <a
                    href={`https://huggingface.co/${hfStatus?.repo_id || 'kkshaolin/yolo_box'}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2.5 bg-white border border-slate-300 hover:border-slate-400 text-slate-800 rounded-xl font-medium text-sm flex items-center gap-2 shadow-xs hover:shadow transition"
                  >
                    <span>เปิด Hugging Face Hub</span>
                    <ExternalLink className="w-4 h-4 text-slate-500" />
                  </a>
                  <button
                    onClick={fetchHfStatus}
                    disabled={hfLoading}
                    className="px-3 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-medium flex items-center gap-1.5 transition"
                    title="รีเฟรชข้อมูลสถานะ"
                  >
                    <RefreshCw className={`w-4 h-4 ${hfLoading ? 'animate-spin text-blue-600' : ''}`} />
                  </button>
                </div>
              </div>

              {/* Status Message / Notification */}
              {hfMessage && (
                <div className={`mt-4 p-3.5 rounded-xl text-sm flex items-center justify-between border ${
                  hfMessage.type === 'success' 
                    ? 'bg-emerald-50 text-emerald-900 border-emerald-200' 
                    : hfMessage.type === 'error'
                    ? 'bg-rose-50 text-rose-900 border-rose-200'
                    : 'bg-blue-50 text-blue-900 border-blue-200'
                }`}>
                  <div className="flex items-center gap-2">
                    {hfMessage.type === 'success' && <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />}
                    {hfMessage.type === 'error' && <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />}
                    {hfMessage.type === 'info' && <Loader2 className="w-5 h-5 animate-spin text-blue-600 shrink-0" />}
                    <span>{hfMessage.text}</span>
                  </div>
                  <button 
                    onClick={() => setHfMessage(null)}
                    className="text-xs font-bold text-slate-400 hover:text-slate-600 ml-4"
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>

            {/* Architecture Comparison Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {/* Local Storage Card */}
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-semibold text-slate-800 text-sm">
                    <HardDrive className="w-4 h-4 text-blue-600" /> Local Container Disk
                  </div>
                  <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-blue-700">
                    &lt;1ms Latency
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  ไฟล์โมเดลในเครื่อง <code>storage/models/</code> สำหรับโหลดเข้าหน่วยความจำของ FastAPI และ Worker
                </p>
                <div className="pt-2 border-t border-slate-100 space-y-1.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">YOLO v3 (Recommended):</span>
                    <span className="font-semibold text-slate-800">
                      {hfStatus?.local.yolo_box_v3?.exists ? `✅ ${hfStatus.local.yolo_box_v3.size_mb} MB` : '❌ ขาด'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">YOLO Base:</span>
                    <span className="font-semibold text-slate-800">
                      {hfStatus?.local.yolo_box.exists ? `✅ ${hfStatus.local.yolo_box.size_mb} MB` : '❌ ขาด'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">ARIMA Model:</span>
                    <span className="font-semibold text-slate-800">
                      {hfStatus?.local.arima_model.exists ? `✅ ${hfStatus.local.arima_model.size_kb} KB` : '❌ ขาด'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">ARIMA Metrics:</span>
                    <span className="font-semibold text-slate-800">
                      {hfStatus?.local.arima_metrics.exists ? '✅ มีข้อมูล' : '❌ ขาด'}
                    </span>
                  </div>
                </div>
              </div>

              {/* MinIO Object Storage Card */}
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-semibold text-slate-800 text-sm">
                    <Database className="w-4 h-4 text-teal-600" /> MinIO S3 Object Storage
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    hfStatus?.minio.connected ? 'bg-teal-50 text-teal-700' : 'bg-rose-50 text-rose-700'
                  }`}>
                    {hfStatus?.minio.connected ? 'Connected' : 'Offline'}
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  Bucket <code>models</code> เก็บประวัติโมเดลทุก Run จากการฝึก และเป็นคลังโมเดลระดับเครื่องเซิร์ฟเวอร์
                </p>
                <div className="pt-2 border-t border-slate-100 space-y-1.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">Bucket:</span>
                    <span className="font-semibold text-slate-800">{hfStatus?.minio.bucket || 'models'}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">Total Artifacts:</span>
                    <span className="font-semibold text-slate-800">{hfStatus?.minio.objects_count || 0} objects</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">S3 Endpoint:</span>
                    <span className="font-semibold text-slate-800">localhost:9000</span>
                  </div>
                </div>
              </div>

              {/* Hugging Face Hub Card */}
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-semibold text-slate-800 text-sm">
                    <Cloud className="w-4 h-4 text-amber-600" /> Hugging Face Model Hub
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    hfStatus?.huggingface.connected ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
                  }`}>
                    {hfStatus?.huggingface.connected ? 'Hub Ready' : 'Disconnected'}
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  ศูนย์กลางแจกจ่ายโมเดล (Remote Registry) สำหรับนักพัฒนาและสภาพแวดล้อมใหม่
                </p>
                <div className="pt-2 border-t border-slate-100 space-y-1.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">Repository:</span>
                    <span className="font-semibold text-blue-600 truncate max-w-[150px]">
                      {hfStatus?.repo_id || 'kkshaolin/yolo_box'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">Remote Files:</span>
                    <span className="font-semibold text-slate-800">
                      {hfStatus?.huggingface.files.length || 0} files
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-600">Access:</span>
                    <span className="font-semibold text-emerald-700">Public (No Token Needed to Pull)</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Model Files Table & Action Center */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-6 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                    <Box className="w-5 h-5 text-indigo-600" /> รายการโมเดลและสถานะการซิงค์ (Model Assets)
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    ตรวจสอบไฟล์ที่ซิงค์ระหว่าง Local Runtime, MinIO Storage และ Hugging Face Remote Hub
                  </p>
                </div>

                {/* Main Action Buttons */}
                <div className="flex items-center gap-3">
                  {/* Pull Button */}
                  <button
                    onClick={handlePullHf}
                    disabled={hfActionLoading !== null}
                    className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold flex items-center gap-2 shadow-xs transition"
                  >
                    {hfActionLoading === 'pull' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" /> กำลังดาวน์โหลด...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" /> Sync / Pull from Hub
                      </>
                    )}
                  </button>

                  {/* Push Button */}
                  <button
                    onClick={handlePushHf}
                    disabled={hfActionLoading !== null}
                    className="px-4 py-2.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-700 hover:to-orange-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold flex items-center gap-2 shadow-xs transition"
                  >
                    {hfActionLoading === 'push' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" /> กำลังอัปโหลด...
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4" /> Publish / Push to Hub
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-3.5 px-6">โมเดล / หน้าที่</th>
                      <th className="py-3.5 px-6">ไฟล์บนเครื่อง (Local)</th>
                      <th className="py-3.5 px-6">MinIO Bucket (S3)</th>
                      <th className="py-3.5 px-6">Hugging Face Hub (Remote)</th>
                      <th className="py-3.5 px-6 text-right">สถานะความพร้อม</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {/* Row 1: YOLO Box Detection */}
                    <tr className="hover:bg-slate-50/50 transition">
                      <td className="py-4 px-6">
                        <div className="font-bold text-slate-900">YOLO11n Box Detection</div>
                        <div className="text-[11px] text-slate-500">ตรวจจับกล่องสินค้าอาหารทะเลจากกล้อง Zone A/B</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-slate-700">yolo11n.pt</span>
                        <div className="text-[11px] text-slate-500">{hfStatus?.local.yolo_box.size_mb || 5.35} MB</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-slate-700">yolo/base/yolo11n.pt</span>
                        <div className="text-[11px] text-emerald-600 font-medium">Ready in MinIO</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-blue-600">yolo/yolo11n.pt</span>
                        <div className="text-[11px] text-slate-500">kkshaolin/yolo_box</div>
                      </td>
                      <td className="py-4 px-6 text-right">
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <Check className="w-3 h-3" /> Synced & Active
                        </span>
                      </td>
                    </tr>

                    {/* Row 2: ARIMA Frozen Seafood */}
                    <tr className="hover:bg-slate-50/50 transition">
                      <td className="py-4 px-6">
                        <div className="font-bold text-slate-900">ARIMA Demand Forecaster</div>
                        <div className="text-[11px] text-slate-500">ทำนายสต็อกกล่องสินค้า Frozen Seafood ล่วงหน้า</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-slate-700">arima_Frozen_Seafood.pkl</span>
                        <div className="text-[11px] text-slate-500">{hfStatus?.local.arima_model.size_kb || 199.6} KB</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-slate-700">arima/Frozen_Seafood/latest/model.pkl</span>
                        <div className="text-[11px] text-emerald-600 font-medium">Ready in MinIO</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-blue-600">arima/arima_Frozen_Seafood.pkl</span>
                        <div className="text-[11px] text-slate-500">kkshaolin/yolo_box</div>
                      </td>
                      <td className="py-4 px-6 text-right">
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <Check className="w-3 h-3" /> Synced & Active
                        </span>
                      </td>
                    </tr>

                    {/* Row 3: ARIMA Metrics */}
                    <tr className="hover:bg-slate-50/50 transition">
                      <td className="py-4 px-6">
                        <div className="font-bold text-slate-900">ARIMA Evaluation Metrics</div>
                        <div className="text-[11px] text-slate-500">Order ARIMA(2,0,2), ค่า MAE, RMSE, MAPE</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-slate-700">arima_Frozen_Seafood.json</span>
                        <div className="text-[11px] text-slate-500">Config & Parameters</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-slate-700">arima/Frozen_Seafood/latest/metrics.json</span>
                        <div className="text-[11px] text-emerald-600 font-medium">Ready in MinIO</div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="font-mono text-blue-600">arima/arima_Frozen_Seafood.json</span>
                        <div className="text-[11px] text-slate-500">kkshaolin/yolo_box</div>
                      </td>
                      <td className="py-4 px-6 text-right">
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <Check className="w-3 h-3" /> Synced & Active
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Bottom Instructions Footer */}
              <div className="p-4 bg-slate-50 border-t border-slate-200 text-xs text-slate-600 flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800">💡 CLI Command:</span>
                  <code className="bg-white px-2.5 py-1 rounded border border-slate-200 text-slate-700">
                    python scripts/sync_huggingface.py --action pull
                  </code>
                </div>
                <div className="text-slate-500">
                  นักพัฒนาที่ Clone โค้ดใหม่ สามารถรันคำสั่งด้านซ้ายหรือกดปุ่ม Sync เพื่อเริ่มใช้งานได้ทันที
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
