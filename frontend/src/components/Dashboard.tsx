// React ใช้สร้างหน้าจอและจัดการ state, effect และการอ้างอิง element ของ DOM
import React, { useState, useEffect } from 'react';
// ส่วนประกอบกราฟสำหรับแสดงข้อมูลสต็อกจริงและผลพยากรณ์ในแกนเวลาเดียวกัน
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer, ComposedChart, Area
} from 'recharts';
// ไอคอนที่ใช้ประกอบปุ่ม หัวข้อ และการ์ดสรุปในหน้า Dashboard
import { 
  Activity, Box, Camera, AlertTriangle, TrendingUp, Settings, PlayCircle, RefreshCw
} from 'lucide-react';

// ฟังก์ชันเรียก API แยกตามความรับผิดชอบ: สต็อก, กล้อง, พยากรณ์, ตั้งค่า และประเมินความเสี่ยง
import { getStockSummary, getStockHistory, getStockProducts } from '../api/stock';
import { getLatestCameraLog, getCameraLogsHistory } from '../api/camera';
import { queueForecast, getForecastJobStatus, queueTraining, getLatestForecast } from '../api/forecast';
import { getSettings, updateSettings } from '../api/settings';
import { evaluateRisk } from '../api/risk';

export const Dashboard = () => {
  // ใช้ควบคุมสถานะกำลังทำงานและข้อความที่แสดงใน loading overlay
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  
  // กำหนดสินค้าเริ่มต้น รวมถึงช่วงเวลาพยากรณ์และกล้องที่เลือก
  const PRODUCT_NAME = "Premium_White_Shrimp";
  const [horizon, setHorizon] = useState(3);
  const [cameraId, setCameraId] = useState('cam_main');
  
  // เก็บข้อมูลจาก API เพื่อให้ส่วนแสดงผลอัปเดตตามข้อมูลล่าสุด
  // summary, cameraLog และ cameraHistory ถูกโหลดไว้ แต่ยังไม่ได้ใช้แสดงผลใน UI ปัจจุบัน
  const [summary, setSummary] = useState<any>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [forecastData, setForecastData] = useState<any>(null);
  const [cameraLog, setCameraLog] = useState<any>(null);
  const [cameraHistory, setCameraHistory] = useState<any[]>([]);

  // เก็บค่าตั้งค่าระบบ, สถานะเปิด/ปิดหน้าต่างตั้งค่า และผลประเมินความเสี่ยง
  const [settings, setSettings] = useState<any>({});
  const [showSettings, setShowSettings] = useState(false);
  const [riskData, setRiskData] = useState<any>(null);

  // ค่า prototype สำหรับโหมดกล้องจริง; ตอนนี้ไม่มีปุ่มเปลี่ยนค่านี้ จึงยังเข้า branch สตรีมจริงไม่ได้
  const [isLiveCamera, setIsLiveCamera] = useState(false);

  // โหลดข้อมูลทั้งหมดที่หน้า Dashboard ต้องใช้จาก API
  const loadDashboardData = async () => {
    try {
      // โหลดค่าตั้งค่าก่อน เพื่อใช้ค่า forecast horizon ปัจจุบันกับหน้าจอ
      let loadedSettings = settings;
      try {
        loadedSettings = await getSettings();
        setSettings(loadedSettings);
        if (loadedSettings.forecast_horizon) setHorizon(parseInt(loadedSettings.forecast_horizon));
      } catch (e) { console.error(e); }

      // โหลดภาพรวมสต็อก แล้วเก็บไว้ใน state สำหรับการแสดงผล
      const sum = await getStockSummary();
      setSummary(sum);

      // โหลดประวัติของสินค้า และจัดรูปวันที่/ปริมาณให้อยู่ในรูปแบบที่กราฟใช้ได้
      const hist = await getStockHistory(PRODUCT_NAME);
      if (hist?.data) {
        const formatted = hist.data.map((r: any) => ({
          date: new Date(r.recorded_at).toISOString().split('T')[0].substring(0, 7), // YYYY-MM
          quantity: r.quantity
        }));
        
        // รวมปริมาณที่มีวันที่อยู่ในเดือนเดียวกัน เพื่อให้กราฟสรุปเป็นรายเดือน
        const monthlyMap = new Map();
        formatted.forEach((r: any) => {
          if (!monthlyMap.has(r.date)) monthlyMap.set(r.date, 0);
          monthlyMap.set(r.date, monthlyMap.get(r.date) + r.quantity);
        });
        
        const chartData = Array.from(monthlyMap.entries()).map(([date, quantity]) => ({ date, quantity }));
        setHistoryData(chartData);
      }
      
      // เรียกผลพยากรณ์ล่าสุดที่บันทึกไว้ เพื่อแสดงผลเดิมทันทีโดยไม่ต้องรันโมเดลใหม่
      try {
        const latestForecast = await getLatestForecast(PRODUCT_NAME);
        if (latestForecast && latestForecast.forecast.length > 0) {
          setForecastData(latestForecast);
        }
      } catch (e) {
        console.log("No previous forecast found in DB.");
      }

      // Prepared camera API calls; the current backend does not register camera routes yet.
      try {
        const cam = await getLatestCameraLog(cameraId);
        setCameraLog(cam);
        const camHist = await getCameraLogsHistory(cameraId);
        setCameraHistory(camHist?.logs || []);
      } catch (e) {
        console.warn("Camera logs not available yet");
      }
    } catch (e) {
      console.error("Failed to load dashboard data:", e);
    }
  };

  // โหลดชุดข้อมูลครั้งแรก และโหลดข้อมูลกล้องใหม่เมื่อผู้ใช้เปลี่ยนแหล่งกล้อง
  useEffect(() => {
    loadDashboardData();
  }, [cameraId]);

  // คำนวณความเสี่ยงใหม่เมื่อประวัติสต็อก ผลพยากรณ์ หรือค่าตั้งค่าที่เกี่ยวข้องเปลี่ยน
  useEffect(() => {
    const checkRisk = async () => {
      // ใช้ปริมาณล่าสุดในประวัติเทียบกับค่าพยากรณ์งวดถัดไป
      const currentStock = historyData.length > 0 ? historyData[historyData.length - 1].quantity : 0;
      const nextForecast = forecastData?.forecast?.[0]?.predicted_value;
      
      // ประเมินได้เมื่อมีข้อมูลสต็อก/พยากรณ์และผู้ใช้กำหนดเกณฑ์สต็อกต่ำแล้ว
      if (currentStock !== undefined && nextForecast !== undefined && settings.low_stock_threshold) {
        try {
          const r = await evaluateRisk({
            current_stock: currentStock,
            forecast_stock: nextForecast,
            threshold: parseFloat(settings.low_stock_threshold),
            risk_preference: settings.risk_preference || 'balanced'
          });
          setRiskData(r);
        } catch (e) { console.error(e); }
      } else {
        setRiskData(null);
      }
    };
    checkRisk();
  }, [historyData, forecastData, settings]);

  // ขอให้ backend สร้างงานพยากรณ์ แล้วตรวจสอบสถานะงานจนเสร็จ ล้มเหลว หรือหมดเวลา
  const runForecast = async () => {
    setLoading(true);
    setStatusMsg('Queuing Forecast Job...');
    // ล้างผลเก่าเพื่อไม่ให้ผู้ใช้เข้าใจผิดว่าเป็นผลจากคำขอครั้งใหม่
    setForecastData(null);
    try {
      const res = await queueForecast({
        product: PRODUCT_NAME,
        forecast_horizon: horizon,
        p: 1, d: 1, q: 1
      });
      
      const jobId = res.job_id;
      setStatusMsg('Model Training in Progress...');
      
      // ตรวจสถานะงานเป็นระยะ เพราะ backend ประมวลผลแบบ asynchronous
      const poll = setInterval(async () => {
        try {
          const statusRes = await getForecastJobStatus(jobId);
          if (statusRes.status === 'completed') {
            clearInterval(poll);
            setForecastData(statusRes.result);
            setLoading(false);
            setStatusMsg('');
          } else if (statusRes.status === 'failed') {
            clearInterval(poll);
            alert("Forecast failed: " + statusRes.error);
            setLoading(false);
            setStatusMsg('');
          }
        } catch (pollErr) {
          console.error(pollErr);
        }
      }, 2000);
      
      // หยุดติดตามหลัง 60 วินาที เพื่อไม่ให้มีการ polling ค้างไม่สิ้นสุด
      setTimeout(() => {
        clearInterval(poll);
        if (loading) {
          setLoading(false);
          setStatusMsg('');
          alert("Forecast timed out.");
        }
      }, 60000);

    } catch (err: any) {
      alert("Failed to queue forecast: " + (err.response?.data?.detail || err.message));
      setLoading(false);
      setStatusMsg('');
    }
  };

  // ขอให้ backend ฝึกโมเดล โดยติดตามสถานะงานและแจ้งผลเช่นเดียวกับงานพยากรณ์
  const runTraining = async () => {
    setLoading(true);
    setStatusMsg('Queuing Training Job...');
    try {
      const res = await queueTraining({
        product: PRODUCT_NAME,
        forecast_horizon: horizon,
        p: 1, d: 1, q: 1
      });
      
      const jobId = res.job_id;
      setStatusMsg('Model Training in Progress...');
      
      // งานฝึกโมเดลทำงานเบื้องหลัง จึงตรวจสอบสถานะทุก 2 วินาที
      const poll = setInterval(async () => {
        try {
          const statusRes = await getForecastJobStatus(jobId);
          if (statusRes.status === 'completed') {
            clearInterval(poll);
            alert("Training completed successfully!");
            setLoading(false);
            setStatusMsg('');
          } else if (statusRes.status === 'failed') {
            clearInterval(poll);
            alert("Training failed: " + statusRes.error);
            setLoading(false);
            setStatusMsg('');
          }
        } catch (pollErr) {
          console.error(pollErr);
        }
      }, 2000);
      
      // ป้องกันการรอผลจากงานฝึกโมเดลนานเกินกำหนด
      setTimeout(() => {
        clearInterval(poll);
        if (loading) {
          setLoading(false);
          setStatusMsg('');
          alert("Training timed out.");
        }
      }, 60000);

    } catch (err: any) {
      alert("Failed to queue training: " + (err.response?.data?.detail || err.message));
      setLoading(false);
      setStatusMsg('');
    }
  };

  // รวมประวัติ 9 เดือนล่าสุดกับค่าพยากรณ์ เพื่อใช้เป็นชุดข้อมูลเดียวของกราฟ
  let combinedChartData: any[] = JSON.parse(JSON.stringify([...historyData].slice(-9)));
  if (forecastData && forecastData.forecast && forecastData.forecast.length > 0) {
    if (combinedChartData.length > 0) {
      const lastIndex = combinedChartData.length - 1;
      // กำหนดจุดเริ่มต้นของเส้นพยากรณ์ให้ต่อเนื่องจากค่าจริงเดือนล่าสุด
      combinedChartData[lastIndex].forecast = combinedChartData[lastIndex].quantity;
      combinedChartData[lastIndex].lower = combinedChartData[lastIndex].quantity;
      combinedChartData[lastIndex].upper = combinedChartData[lastIndex].quantity;
    }

    // แปลงรายการ forecast ให้ใช้ชื่อ field และรูปแบบวันที่เดียวกับข้อมูลประวัติ
    let fData = forecastData.forecast.map((f: any) => ({
      date: f.date.substring(0, 7),
      forecast: f.predicted_value,
      lower: f.lower_bound,
      upper: f.upper_bound
    }));

    // ถ้าจุดพยากรณ์แรกอยู่ในเดือนเดียวกับข้อมูลจริงล่าสุด ให้รวมเป็นจุดเดียวบนกราฟ
    if (combinedChartData.length > 0 && fData.length > 0 && combinedChartData[combinedChartData.length - 1].date === fData[0].date) {
      combinedChartData[combinedChartData.length - 1] = { ...combinedChartData[combinedChartData.length - 1], ...fData[0] };
      fData.shift();
    }

    combinedChartData = [...combinedChartData, ...fData];
  }

  // คำนวณค่าเฉลี่ยของปริมาณตามข้อมูลรายเดือนที่แสดงในประวัติ
  const avgStock = historyData.length > 0 
    ? (historyData.reduce((acc, curr) => acc + curr.quantity, 0) / historyData.length).toFixed(0) 
    : 0;

  // เตรียมค่าที่การ์ดสรุปใช้: สต็อกล่าสุด, ค่าพยากรณ์งวดแรก และสถานะตามเกณฑ์ที่กำหนด
  const currentStock = historyData.length > 0 ? historyData[historyData.length - 1].quantity : 0;
  const nextForecast = forecastData?.forecast?.[0]?.predicted_value?.toFixed(0) || '-';
  // ค่าคำนวณเกณฑ์แบบเดิมยังเก็บไว้แต่ไม่ได้ใช้; การ์ดความเสี่ยงใช้ผลจาก evaluateRisk ของ backend
  const isRisk = nextForecast !== '-' && parseInt(nextForecast) > 1500;

  return (
    <div className="flex h-screen bg-gray-50 font-sans text-sm">
      {/* แถบด้านข้าง: ชื่อระบบ, ตัวเลือกคลัง/กล้อง และปุ่มนำเข้าข้อมูลกับสั่งงานโมเดล */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-200">
          <h1 className="text-lg font-bold text-blue-600 flex items-center gap-2">
            <Box className="w-5 h-5" /> ShrimpStock AI
          </h1>
        </div>
        <div className="p-4 flex-1 overflow-y-auto space-y-6">

          
          <div className="space-y-2">
            {/* ตัวเลือกคลังเป็น UI ตัวอย่าง ยังไม่ได้ผูก state หรือกรองข้อมูล API */}
            <label className="font-semibold text-gray-700">Warehouse</label>
            <select className="w-full p-2 border rounded text-gray-700 bg-white">
              <option>All Zones</option>
              <option>Zone A (Cold Storage)</option>
              <option>Zone B (Processing)</option>
            </select>
          </div>

          <div className="space-y-2">
            <label className="font-semibold text-gray-700">Camera Source</label>
            {/* เปลี่ยน cameraId เพื่อทดลองเลือกกล้อง; API ของกล้องยังไม่พร้อมใน backend ปัจจุบัน */}
            <select 
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
              className="w-full p-2 border rounded text-gray-700 bg-white"
            >
              <option value="cam_main">Cam-Main (Zone A)</option>
              <option value="cam_dock">Cam-Dock (Zone B)</option>
            </select>
          </div>
        </div>
        
        <div className="p-4 border-t border-gray-200 space-y-3">
          <button 
            onClick={runForecast}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white p-2 rounded transition font-medium"
          >
            <PlayCircle className="w-4 h-4" /> Run Prediction
          </button>
          <button 
            onClick={runTraining}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 text-white p-2 rounded transition font-medium"
          >
            <Settings className="w-4 h-4" /> Train Model
          </button>
        </div>
      </aside>

      {/* พื้นที่เนื้อหาหลัก แบ่งเป็นหัวหน้าจอและเนื้อหาที่เลื่อนดูได้ */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* หัวหน้าจอ: รีเฟรชข้อมูล เปิดหน้าตั้งค่า และแสดงสถานะระบบ */}
        <header className="bg-white border-b border-gray-200 p-4 flex justify-between items-center shrink-0">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-semibold text-gray-800">Dashboard Overview</h2>
            <button onClick={loadDashboardData} className="text-gray-500 hover:text-blue-600 transition" title="Refresh Data">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setShowSettings(true)} className="flex items-center gap-2 text-gray-600 bg-gray-100 px-3 py-1.5 rounded border border-gray-200 hover:bg-gray-200 transition">
              <Settings className="w-4 h-4" />
              <span className="font-medium text-xs">Settings</span>
            </button>
            {/* ป้ายสถานะนี้เป็นข้อความคงที่ ยังไม่ได้อ่านผลจาก /health */}
            <div className="flex items-center gap-2 text-green-600 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">
              <Activity className="w-4 h-4" />
              <span className="font-medium text-xs">System Online</span>
            </div>
          </div>
        </header>

        {/* เนื้อหา Dashboard แบบเลื่อนได้; overlay จะแสดงระหว่างอัปโหลดหรือรอโมเดล */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 relative">
          {loading && (
            <div className="absolute inset-0 bg-white/60 backdrop-blur-sm z-20 flex items-center justify-center rounded-xl">
              <div className="flex flex-col items-center gap-3 bg-white p-6 rounded-xl shadow-xl border border-gray-100">
                <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                <p className="font-semibold text-blue-700 text-lg">{statusMsg}</p>
                <p className="text-xs text-gray-500">Please wait, ARIMA is fitting the model...</p>
              </div>
            </div>
          )}

          {/* การ์ดสรุป: ปริมาณปัจจุบัน ค่าเฉลี่ย ค่าพยากรณ์ถัดไป และผลประเมินความเสี่ยง */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
              <div className="text-gray-500 mb-1 flex items-center justify-between">
                <span>Current Stock</span>
                <Box className="w-4 h-4 text-blue-500" />
              </div>
              <div className="text-2xl font-bold text-gray-800">{currentStock.toLocaleString()} kg</div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
              <div className="text-gray-500 mb-1 flex items-center justify-between">
                <span>Average Monthly</span>
                <Activity className="w-4 h-4 text-purple-500" />
              </div>
              <div className="text-2xl font-bold text-gray-800">{avgStock} kg</div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
              <div className="text-gray-500 mb-1 flex items-center justify-between">
                <span>Forecast (Next)</span>
                <TrendingUp className="w-4 h-4 text-emerald-500" />
              </div>
              <div className="text-2xl font-bold text-gray-800">{nextForecast} kg</div>
            </div>
            <div className={`p-4 rounded-xl border shadow-sm ${
              riskData?.risk_level === 'Critical' ? 'bg-red-50 border-red-200' 
              : riskData?.risk_level === 'Warning' ? 'bg-orange-50 border-orange-200'
              : 'bg-green-50 border-green-200'
            }`}>
              <div className={`${
                riskData?.risk_level === 'Critical' ? 'text-red-700' 
                : riskData?.risk_level === 'Warning' ? 'text-orange-700' 
                : 'text-green-700'
              } mb-1 flex items-center justify-between`}>
                <span>Risk Status</span>
                <AlertTriangle className={`w-4 h-4 ${
                  riskData?.risk_level === 'Critical' ? 'text-red-500' 
                  : riskData?.risk_level === 'Warning' ? 'text-orange-500' 
                  : 'text-green-500'
                }`} />
              </div>
              <div className={`text-2xl font-bold ${
                riskData?.risk_level === 'Critical' ? 'text-red-800' 
                : riskData?.risk_level === 'Warning' ? 'text-orange-800' 
                : 'text-green-800'
              }`}>
                {riskData?.risk_level || (nextForecast !== '-' ? 'Evaluating...' : 'Unknown')}
              </div>
              <div className={`text-xs mt-2 ${
                riskData?.risk_level === 'Critical' ? 'text-red-600' 
                : riskData?.risk_level === 'Warning' ? 'text-orange-600' 
                : 'text-green-600'
              }`}>
                {riskData?.reason || (nextForecast !== '-' ? 'Waiting for model forecast' : 'Run forecast to evaluate risk')}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-6">
            {/* คอลัมน์กราฟและข้อมูลโมเดล */}
            <div className="col-span-2 space-y-6">
              {/* กราฟแสดงประวัติจริงและค่าพยากรณ์พร้อมขอบเขตค่าต่ำ/สูง */}
              <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm">
                <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" /> Stock History & ARIMA Forecast
                </h3>
                <div className="h-80 w-full">
                  {combinedChartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={combinedChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                        <XAxis dataKey="date" tick={{fontSize: 12}} tickMargin={10} />
                        <YAxis tick={{fontSize: 12}} domain={['auto', 'auto']} />
                        <RechartsTooltip />
                        <Legend wrapperStyle={{fontSize: 12, paddingTop: '10px'}}/>
                        <Area type="monotone" dataKey="upper" stroke="none" fill="#DBEAFE" />
                        <Area type="monotone" dataKey="lower" stroke="none" fill="#ffffff" />
                        <Line type="monotone" dataKey="quantity" name="Actual" stroke="#3B82F6" strokeWidth={2} dot={{r: 4}} />
                        <Line type="monotone" dataKey="forecast" name="Forecast" stroke="#10B981" strokeWidth={2} strokeDasharray="5 5" dot={{r: 4}} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-400 bg-gray-50 rounded-lg border border-dashed border-gray-200">
                      No historical data available.
                    </div>
                  )}
                </div>
              </div>

              {/* รายละเอียดโมเดลและตัวชี้วัดจะแสดงเมื่อมีผลพยากรณ์แล้วเท่านั้น */}
              {forecastData && (
                <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm">
                  {/* หัวข้อเป็นชื่อส่วนแสดงผล; URI อาจเป็น local path ไม่ได้ยืนยันว่า register ใน MLflow แล้ว */}
                  <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                    <Settings className="w-4 h-4" /> Model Information (MLflow)
                  </h3>
                  <div className="grid grid-cols-5 gap-4 bg-gray-50 p-4 rounded-lg border border-gray-100">
                    <div>
                      <div className="text-xs text-gray-500">Algorithm</div>
                      <div className="font-semibold text-gray-800">{forecastData.model_name}</div>
                    </div>
                    <div className="col-span-2 overflow-hidden text-ellipsis whitespace-nowrap">
                      <div className="text-xs text-gray-500">Model URI</div>
                      <div className="font-semibold text-gray-800 text-xs mt-1" title={forecastData.model_uri}>{forecastData.model_uri || 'Not saved to MLflow'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500">MAE</div>
                      <div className="font-semibold text-green-600">{forecastData.metrics?.mae?.toFixed(2) || 0}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500">MAPE</div>
                      <div className="font-semibold text-green-600">{forecastData.metrics?.mape?.toFixed(2) || 0}%</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* คอลัมน์ที่ 3: ส่วนแสดงภาพจากกล้อง */}
            <div className="col-span-1 space-y-6">
              <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col h-full">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                    <Camera className="w-4 h-4" /> Live Camera View
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"></span>
                    </span>
                    <span className="text-xs text-gray-500 font-medium">LIVE</span>
                  </div>
                </div>
                
                <div className="flex-1 bg-black rounded-lg overflow-hidden relative min-h-[250px] flex items-center justify-center border border-gray-800">
                  {!isLiveCamera ? (
                    // โหมดจำลองใช้รูปใน storage ไม่ใช่ภาพสด; ไฟล์นี้อาจไม่มีใน checkout ใหม่
                    <img  src="/ex.jpg" 
                          alt="Mock Camera Feed" 
                          className="w-full h-full object-cover opacity-90"
                    />
                  ) : (
                    // โหมดกล้องจริงยังเป็น placeholder; ยังไม่มี stream source หรือ UI เปิดโหมดนี้
                    <div className="w-full h-full flex flex-col items-center justify-center text-gray-500 gap-2">
                      {/* 
                        TODO: ใส่ <video> หรือ <img> สำหรับสตรีมจริงที่นี่ 
                        เช่น: <video id="live-stream" autoPlay playsInline className="w-full h-full object-cover"></video>
                      */}
                      <Camera className="w-8 h-8 opacity-50" />
                      <p className="text-sm text-center px-4">Real camera stream goes here.<br/>Ready for integration.</p>
                    </div>
                  )}
                  
                  {/* Overlay ข้อมูลกล้อง */}
                  <div className="absolute bottom-3 left-3 bg-black/60 backdrop-blur-sm text-white text-xs px-2 py-1 rounded">
                    {cameraId === 'cam_main' ? 'Zone A (Cold Storage)' : 'Zone B (Processing)'}
                  </div>
                  <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-sm text-white text-xs px-2 py-1 rounded font-mono">
                    {new Date().toLocaleTimeString()}
                  </div>
                </div>
                
                <div className="mt-4 text-xs text-gray-500">
                  <p><strong>Note:</strong> Currently in mock mode using placeholder image (`/storage/data/ex.jpg`).</p>
                </div>
              </div>
            </div>
            </div>
          </div>
      </main>

      {/* หน้าต่างตั้งค่า: เปิดเมื่อผู้ใช้กด Settings และปิดหลังบันทึกหรือยกเลิก */}
      {showSettings && (
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
              <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
                <Settings className="w-5 h-5 text-blue-600" /> System Settings
              </h2>
              <button onClick={() => setShowSettings(false)} className="text-gray-400 hover:text-gray-600">✕</button>
            </div>
            
            {/* ป้องกันการ submit แบบ reload หน้า แล้วบันทึกค่าตั้งค่าผ่าน API */}
            <form onSubmit={async (e) => {
              e.preventDefault();
              setLoading(true);
              try {
                await updateSettings({
                  risk_preference: settings.risk_preference,
                  low_stock_threshold: settings.low_stock_threshold,
                  forecast_horizon: settings.forecast_horizon,
                  default_product: settings.default_product
                });
                setShowSettings(false);
                loadDashboardData();
              } catch (err: any) {
                alert("Failed to save settings: " + err.message);
              } finally {
                setLoading(false);
              }
            }} className="p-6 space-y-4">
              
              {/* เลือกความเข้มงวดของการประเมินความเสี่ยง */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-gray-600 uppercase">Risk Preference</label>
                <select 
                  value={settings.risk_preference || 'balanced'} 
                  onChange={(e) => setSettings({...settings, risk_preference: e.target.value})}
                  className="w-full p-2 border border-gray-200 rounded focus:ring-2 focus:ring-blue-100 outline-none"
                >
                  <option value="conservative">Conservative (Warn early, keep high stock)</option>
                  <option value="balanced">Balanced (Standard thresholds)</option>
                  <option value="aggressive">Aggressive (Lean stock, tolerate lower levels)</option>
                </select>
              </div>

              {/* กำหนดระดับสต็อกที่ใช้เป็นเกณฑ์แจ้งเตือนความเสี่ยง */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-gray-600 uppercase">Low Stock Threshold (kg)</label>
                <input 
                  type="number" 
                  value={settings.low_stock_threshold || ''}
                  onChange={(e) => setSettings({...settings, low_stock_threshold: e.target.value})}
                  className="w-full p-2 border border-gray-200 rounded focus:ring-2 focus:ring-blue-100 outline-none"
                  required
                />
              </div>

              {/* กำหนดจำนวนช่วงเวลาล่วงหน้าที่ต้องการให้โมเดลพยากรณ์ */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-gray-600 uppercase">Default Forecast Horizon</label>
                <input 
                  type="number" 
                  value={settings.forecast_horizon || ''}
                  onChange={(e) => setSettings({...settings, forecast_horizon: e.target.value})}
                  className="w-full p-2 border border-gray-200 rounded focus:ring-2 focus:ring-blue-100 outline-none"
                  required
                />
              </div>



              <div className="pt-4 flex gap-3 justify-end">
                <button type="button" onClick={() => setShowSettings(false)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded">Cancel</button>
                <button type="submit" disabled={loading} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded shadow-sm disabled:opacity-50">
                  Save Settings
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

    </div>
  );
};
