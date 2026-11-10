import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { 
  FileText, 
  UploadCloud, 
  Search, 
  Trash2, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  AlertTriangle,
  RotateCw,
  Layers, 
  Database,
  Sparkles,
  Loader2,
  Calendar,
  CalendarDays,
  ShieldCheck,
  Plus,
  Check,
  X,
  Edit3,
  BookOpen,
  Grid3X3,
  List,
  MapPin,
  User as UserIcon,
  HelpCircle,
  Tag
} from 'lucide-react';

const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const CLASS_TYPES = ['Lecture', 'Lab', 'Practical', 'Tutorial', 'Seminar'];

// Helper to convert period numbers to ordinal labels (e.g. 1 -> "1st", 2 -> "2nd")
const getOrdinalLabel = (n) => {
  if (!n) return '1st';
  const num = parseInt(n, 10);
  if (isNaN(num)) return `${n}`;
  const s = ["th", "st", "nd", "rd"];
  const v = num % 100;
  return num + (s[(v - 20) % 10] || s[v] || s[0]);
};

// Helper to parse time strings like "09:00", "09:00 AM", "2 PM" to minutes from midnight
const parseTimeToMinutes = (tStr) => {
  if (!tStr) return null;
  const s = tStr.trim().toUpperCase();
  const m = s.match(/(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?/);
  if (!m) return null;
  let h = parseInt(m[1], 10);
  const min = m[2] ? parseInt(m[2], 10) : 0;
  const meridiem = m[3];
  if (meridiem === 'PM' && h < 12) h += 12;
  else if (meridiem === 'AM' && h === 12) h = 0;
  return h * 60 + min;
};

// Detect conflicting periods on the same day
const findOverlaps = (periods) => {
  const overlaps = [];
  const byDay = {};
  for (const p of periods) {
    const day = p.day_of_week || p.dayOfWeek;
    if (!day) continue;
    if (!byDay[day]) byDay[day] = [];
    byDay[day].push(p);
  }
  for (const day of Object.keys(byDay)) {
    const dayPeriods = byDay[day];
    for (let i = 0; i < dayPeriods.length; i++) {
      for (let j = i + 1; j < dayPeriods.length; j++) {
        const p1 = dayPeriods[i];
        const p2 = dayPeriods[j];
        const s1 = parseTimeToMinutes(p1.start_time || p1.startTime);
        const e1 = parseTimeToMinutes(p1.end_time || p1.endTime);
        const s2 = parseTimeToMinutes(p2.start_time || p2.startTime);
        const e2 = parseTimeToMinutes(p2.end_time || p2.endTime);
        if (s1 !== null && e1 !== null && s2 !== null && e2 !== null) {
          if (Math.max(s1, s2) < Math.min(e1, e2)) {
            const name1 = p1.subject_name || p1.subjectName || 'Class 1';
            const name2 = p2.subject_name || p2.subjectName || 'Class 2';
            const time1 = `${p1.start_time || p1.startTime}-${p1.end_time || p1.endTime}`;
            const time2 = `${p2.start_time || p2.startTime}-${p2.end_time || p2.endTime}`;
            overlaps.push({
              day,
              message: `• ${name1} (${time1}) clashes with ${name2} (${time2}) on ${day}.`
            });
          }
        }
      }
    }
  }
  return overlaps;
};

export const KnowledgePage = () => {
  // Top-level tab: 'rag' | 'timetable'
  const [activeTab, setActiveTab] = useState('timetable');

  // --- RAG State ---
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [docTypeSelection, setDocTypeSelection] = useState('SYLLABUS');
  const [searchQuery, setSearchQuery] = useState('');
  const [queryResult, setQueryResult] = useState(null);
  const [querying, setQuerying] = useState(false);

  // --- Timetable State ---
  const [timetable, setTimetable] = useState(null);
  const [loadingTimetable, setLoadingTimetable] = useState(true);
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'day' | 'list'
  const [selectedDay, setSelectedDay] = useState('Monday');

  // Timetable Editor Modal
  const [editorModal, setEditorModal] = useState({
    isOpen: false,
    mode: 'create', // 'create' | 'edit'
    id: null,
    name: '',
    academicYear: '',
    semester: '',
    section: '',
    periods: [],
    submitting: false,
    error: null
  });

  // Single Period Modal
  const [periodModal, setPeriodModal] = useState({
    isOpen: false,
    mode: 'add', // 'add' | 'edit'
    periodId: null,
    dayOfWeek: 'Monday',
    subjectName: '',
    subjectCode: '',
    startTime: '09:00',
    endTime: '10:00',
    room: '',
    faculty: '',
    classType: 'Lecture',
    notes: '',
    submitting: false,
    error: null
  });

  // Delete Confirmation Modal
  const [deleteConfirm, setDeleteConfirm] = useState({
    isOpen: false,
    type: null, // 'timetable' | 'period'
    id: null,
    periodId: null,
    name: ''
  });

  // Global Alerts
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  // Fetch Documents
  const fetchDocuments = async () => {
    setLoadingDocs(true);
    try {
      const res = await api.getDocuments();
      setDocuments(Array.isArray(res) ? res : []);
    } catch (e) {
      setDocuments([]);
    } finally {
      setLoadingDocs(false);
    }
  };

  // Fetch Timetable
  const fetchTimetable = async () => {
    setLoadingTimetable(true);
    try {
      const res = await api.getTimetable();
      setTimetable(res && res.id ? res : null);
    } catch (e) {
      setTimetable(null);
    } finally {
      setLoadingTimetable(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    fetchTimetable();
  }, []);

  // --- RAG Document Upload Handlers ---
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      let cat = 'notes';
      if (docTypeSelection === 'SYLLABUS' || docTypeSelection === 'APPROVED_SYLLABUS') cat = 'syllabus';
      else if (docTypeSelection === 'TEXTBOOK') cat = 'textbook';

      const res = await api.uploadDocument(file, cat, docTypeSelection);
      setDocuments((prev) => [res, ...prev.filter(d => d.id !== res.id)]);
      setActionSuccess(`Document "${file.name}" indexed successfully into vector memory with ${res.chunkCount || 0} chunks.`);
    } catch (err) {
      setActionError(err.message || "Failed to process and vectorize document.");
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setQuerying(true);
    setActionError(null);
    try {
      const res = await api.queryKnowledge(searchQuery);
      setQueryResult(res);
    } catch (err) {
      setActionError(err.message || "Failed to execute semantic query.");
      setQueryResult(null);
    } finally {
      setQuerying(false);
    }
  };

  const handleDeleteDocument = async (docId) => {
    try {
      await api.deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      setActionSuccess("Document removed from knowledge base.");
    } catch (e) {
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    }
  };

  // --- Timetable Action Handlers ---
  const openCreateTimetableModal = () => {
    setEditorModal({
      isOpen: true,
      mode: 'create',
      id: null,
      name: 'Semester Timetable',
      academicYear: new Date().getFullYear().toString(),
      semester: 'Semester 1',
      section: 'Section A',
      periods: [
        {
          day_of_week: 'Monday',
          subject_name: '',
          subject_code: '',
          start_time: '09:00',
          end_time: '10:00',
          room: '',
          faculty: '',
          class_type: 'Lecture',
          notes: ''
        }
      ],
      submitting: false,
      error: null
    });
  };

  const openEditTimetableModal = () => {
    if (!timetable) return;
    const mappedPeriods = (timetable.periods || []).map(p => ({
      id: p.id,
      day_of_week: p.dayOfWeek || p.day_of_week,
      subject_name: p.subjectName || p.subject_name || '',
      subject_code: p.subjectCode || p.subject_code || '',
      start_time: p.startTime || p.start_time || '09:00',
      end_time: p.endTime || p.end_time || '10:00',
      room: p.room || '',
      faculty: p.faculty || '',
      class_type: p.classType || p.class_type || 'Lecture',
      notes: p.notes || ''
    }));

    setEditorModal({
      isOpen: true,
      mode: 'edit',
      id: timetable.id,
      name: timetable.name || 'Semester Timetable',
      academicYear: timetable.academicYear || '',
      semester: timetable.semester || '',
      section: timetable.section || '',
      periods: mappedPeriods.length > 0 ? mappedPeriods : [
        {
          day_of_week: 'Monday',
          subject_name: '',
          subject_code: '',
          start_time: '09:00',
          end_time: '10:00',
          room: '',
          faculty: '',
          class_type: 'Lecture',
          notes: ''
        }
      ],
      submitting: false,
      error: null
    });
  };

  const handleEditorAddPeriod = () => {
    setEditorModal(prev => ({
      ...prev,
      periods: [
        ...prev.periods,
        {
          day_of_week: prev.periods.length > 0 ? prev.periods[prev.periods.length - 1].day_of_week : 'Monday',
          subject_name: '',
          subject_code: '',
          start_time: '10:00',
          end_time: '11:00',
          room: '',
          faculty: '',
          class_type: 'Lecture',
          notes: ''
        }
      ]
    }));
  };

  const handleEditorPeriodChange = (idx, field, val) => {
    setEditorModal(prev => {
      const updated = [...prev.periods];
      updated[idx] = { ...updated[idx], [field]: val };
      return { ...prev, periods: updated };
    });
  };

  const handleEditorRemovePeriod = (idx) => {
    setEditorModal(prev => ({
      ...prev,
      periods: prev.periods.filter((_, i) => i !== idx)
    }));
  };

  const handleSaveTimetable = async () => {
    if (!editorModal.name.trim()) {
      setEditorModal(prev => ({ ...prev, error: "Timetable name is required." }));
      return;
    }

    // Validate periods
    for (let i = 0; i < editorModal.periods.length; i++) {
      const p = editorModal.periods[i];
      if (!p.subject_name.trim()) {
        setEditorModal(prev => ({ ...prev, error: `Period #${i + 1}: Subject name is required.` }));
        return;
      }
      const sM = parseTimeToMinutes(p.start_time);
      const eM = parseTimeToMinutes(p.end_time);
      if (sM === null || eM === null) {
        setEditorModal(prev => ({ ...prev, error: `Period #${i + 1}: Please enter valid start and end times.` }));
        return;
      }
      if (eM <= sM) {
        setEditorModal(prev => ({ ...prev, error: `Period #${i + 1} (${p.subject_name}): End time must be strictly after start time.` }));
        return;
      }
    }

    setEditorModal(prev => ({ ...prev, submitting: true, error: null }));
    try {
      const payload = {
        name: editorModal.name.trim(),
        academic_year: editorModal.academicYear.trim() || null,
        semester: editorModal.semester.trim() || null,
        section: editorModal.section.trim() || null,
        periods: editorModal.periods.map(p => ({
          day_of_week: p.day_of_week,
          subject_name: p.subject_name.trim(),
          subject_code: p.subject_code.trim() || null,
          start_time: p.start_time.trim(),
          end_time: p.end_time.trim(),
          room: p.room.trim() || null,
          faculty: p.faculty.trim() || null,
          class_type: p.class_type || 'Lecture',
          notes: p.notes.trim() || null
        }))
      };

      let saved;
      if (editorModal.mode === 'create') {
        saved = await api.createTimetable(payload);
        setActionSuccess(`Timetable "${saved.name}" created successfully with ${saved.periods?.length || 0} periods.`);
      } else {
        saved = await api.updateTimetable(editorModal.id, payload);
        setActionSuccess(`Timetable "${saved.name}" updated successfully.`);
      }

      setTimetable(saved);
      setEditorModal(prev => ({ ...prev, isOpen: false, submitting: false }));
    } catch (err) {
      setEditorModal(prev => ({ ...prev, submitting: false, error: err.message || "Failed to save timetable." }));
    }
  };

  // --- Single Period Modal Handlers ---
  const openAddPeriodModal = () => {
    if (!timetable) return;
    setPeriodModal({
      isOpen: true,
      mode: 'add',
      periodId: null,
      periodNumber: '',
      dayOfWeek: selectedDay || 'Monday',
      subjectName: '',
      subjectCode: '',
      startTime: '09:00',
      endTime: '10:00',
      room: '',
      faculty: '',
      classType: 'Lecture',
      notes: '',
      submitting: false,
      error: null
    });
  };

  const openEditPeriodModal = (period) => {
    if (!timetable) return;
    setPeriodModal({
      isOpen: true,
      mode: 'edit',
      periodId: period.id,
      periodNumber: period.periodNumber || period.period_number || '',
      dayOfWeek: period.dayOfWeek || period.day_of_week || 'Monday',
      subjectName: period.subjectName || period.subject_name || '',
      subjectCode: period.subjectCode || period.subject_code || '',
      startTime: period.startTime || period.start_time || '09:00',
      endTime: period.endTime || period.end_time || '10:00',
      room: period.room || '',
      faculty: period.faculty || '',
      classType: period.classType || period.class_type || 'Lecture',
      notes: period.notes || '',
      submitting: false,
      error: null
    });
  };

  const handleSavePeriod = async () => {
    if (!periodModal.subjectName.trim()) {
      setPeriodModal(prev => ({ ...prev, error: "Subject name is required." }));
      return;
    }
    const sM = parseTimeToMinutes(periodModal.startTime);
    const eM = parseTimeToMinutes(periodModal.endTime);
    if (sM === null || eM === null) {
      setPeriodModal(prev => ({ ...prev, error: "Please enter valid start and end times." }));
      return;
    }
    if (eM <= sM) {
      setPeriodModal(prev => ({ ...prev, error: "End time must be after start time." }));
      return;
    }

    setPeriodModal(prev => ({ ...prev, submitting: true, error: null }));
    try {
      const payload = {
        day_of_week: periodModal.dayOfWeek,
        period_number: periodModal.periodNumber ? parseInt(periodModal.periodNumber, 10) : null,
        subject_name: periodModal.subjectName.trim(),
        subject_code: periodModal.subjectCode.trim() || null,
        start_time: periodModal.startTime.trim(),
        end_time: periodModal.endTime.trim(),
        room: periodModal.room.trim() || null,
        faculty: periodModal.faculty.trim() || null,
        class_type: periodModal.classType || 'Lecture',
        notes: periodModal.notes.trim() || null
      };

      if (periodModal.mode === 'add') {
        const newPeriod = await api.addPeriod(timetable.id, payload);
        setTimetable(prev => ({
          ...prev,
          periods: [...(prev.periods || []), newPeriod]
        }));
        setActionSuccess(`Added "${newPeriod.subjectName}" to ${newPeriod.dayOfWeek}.`);
      } else {
        const updatedPeriod = await api.updatePeriod(timetable.id, periodModal.periodId, payload);
        setTimetable(prev => ({
          ...prev,
          periods: (prev.periods || []).map(p => p.id === periodModal.periodId ? updatedPeriod : p)
        }));
        setActionSuccess(`Updated "${updatedPeriod.subjectName}".`);
      }

      setPeriodModal(prev => ({ ...prev, isOpen: false, submitting: false }));
    } catch (err) {
      setPeriodModal(prev => ({ ...prev, submitting: false, error: err.message || "Failed to save period." }));
    }
  };

  // --- Delete Modal Handlers ---
  const confirmDeleteTimetable = () => {
    if (!timetable) return;
    setDeleteConfirm({
      isOpen: true,
      type: 'timetable',
      id: timetable.id,
      periodId: null,
      name: timetable.name || 'Current Timetable'
    });
  };

  const confirmDeletePeriod = (period) => {
    setDeleteConfirm({
      isOpen: true,
      type: 'period',
      id: timetable.id,
      periodId: period.id,
      name: `${period.subjectName} (${period.dayOfWeek})`
    });
  };

  const executeDelete = async () => {
    if (deleteConfirm.type === 'timetable') {
      try {
        await api.deleteTimetable(deleteConfirm.id);
        setTimetable(null);
        setActionSuccess("Timetable deleted successfully.");
      } catch (err) {
        setActionError(err.message || "Failed to delete timetable.");
      }
    } else if (deleteConfirm.type === 'period') {
      try {
        await api.deletePeriod(deleteConfirm.id, deleteConfirm.periodId);
        setTimetable(prev => ({
          ...prev,
          periods: (prev.periods || []).filter(p => p.id !== deleteConfirm.periodId)
        }));
        setActionSuccess("Period deleted successfully.");
      } catch (err) {
        setActionError(err.message || "Failed to delete period.");
      }
    }
    setDeleteConfirm({ isOpen: false, type: null, id: null, periodId: null, name: '' });
  };

  // Calculate Overlaps for Editor Modal
  const editorOverlaps = findOverlaps(editorModal.periods);

  // Group periods for active timetable
  const periodsByDay = {};
  DAYS_OF_WEEK.forEach(d => { periodsByDay[d] = []; });
  (timetable?.periods || []).forEach(p => {
    const d = p.dayOfWeek || p.day_of_week;
    if (periodsByDay[d]) {
      periodsByDay[d].push(p);
    }
  });

  // Sort each day's periods chronologically
  DAYS_OF_WEEK.forEach(d => {
    periodsByDay[d].sort((a, b) => (parseTimeToMinutes(a.startTime || a.start_time) || 0) - (parseTimeToMinutes(b.startTime || b.start_time) || 0));
  });

  // Base days: Monday through Saturday (6 days) by default; Sunday dynamically added if it has entries or is selected
  const baseDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const hasSundayEntries = (periodsByDay['Sunday']?.length || 0) > 0;
  const activeDays = (hasSundayEntries || selectedDay === 'Sunday') ? [...baseDays, 'Sunday'] : baseDays;
  const displayDaysGrid = activeDays;

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Calendar className="text-[#C59A55]" size={26} />
            <span>Academic Knowledge &amp; Timetable</span>
          </h1>
          <p className="text-xs sm:text-sm text-[#A1A4AA] mt-1">
            Maintain your weekly academic timetable and upload course materials for grounded AI recall.
          </p>
        </div>

        {/* Top-Level Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-[#121418] border border-white/10 rounded-xl">
          <button
            onClick={() => setActiveTab('timetable')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'timetable'
                ? 'bg-[#C59A55] text-black font-semibold shadow-md'
                : 'text-[#A1A4AA] hover:text-white hover:bg-white/5'
            }`}
          >
            <Calendar size={15} />
            <span>Academic Timetable</span>
            {timetable && (
              <span className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${
                activeTab === 'timetable' ? 'bg-black/20 text-black' : 'bg-white/10 text-[#C59A55]'
              }`}>
                {timetable.periods?.length || 0}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('rag')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'rag'
                ? 'bg-[#C59A55] text-black font-semibold shadow-md'
                : 'text-[#A1A4AA] hover:text-white hover:bg-white/5'
            }`}
          >
            <BookOpen size={15} />
            <span>Learning Documents &amp; RAG</span>
            <span className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${
              activeTab === 'rag' ? 'bg-black/20 text-black' : 'bg-white/10 text-[#A1A4AA]'
            }`}>
              {documents.length}
            </span>
          </button>
        </div>
      </div>

      {/* Global Alert Banners */}
      {actionError && (
        <div className="p-3.5 rounded-xl bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertCircle size={15} />
            <span>{actionError}</span>
          </div>
          <button onClick={() => setActionError(null)} className="text-[#F07878] hover:text-white font-bold ml-2">✕</button>
        </div>
      )}

      {actionSuccess && (
        <div className="p-3.5 rounded-xl bg-[#42D6A4]/10 border border-[#42D6A4]/30 text-xs text-[#42D6A4] flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={15} />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-[#42D6A4] hover:text-white font-bold ml-2">✕</button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: ACADEMIC TIMETABLE */}
      {/* ========================================================================= */}
      {activeTab === 'timetable' && (
        <div className="space-y-6">
          {loadingTimetable ? (
            <div className="p-16 text-center card-dark rounded-2xl bg-[#121418] border border-white/10">
              <Loader2 size={32} className="mx-auto text-[#C59A55] animate-spin mb-3" />
              <p className="text-xs text-[#A1A4AA] font-mono">Loading your timetable...</p>
            </div>
          ) : !timetable ? (
            /* Empty State */
            <div className="p-12 md:p-16 text-center card-dark rounded-2xl bg-[#121418] border border-white/10 space-y-5 shadow-xl">
              <div className="w-16 h-16 rounded-2xl bg-[#C59A55]/10 border border-[#C59A55]/30 flex items-center justify-center mx-auto text-[#C59A55]">
                <Calendar size={32} />
              </div>
              <div className="space-y-2 max-w-md mx-auto">
                <h3 className="text-lg font-semibold text-white">No Timetable Created Yet</h3>
                <p className="text-xs sm:text-sm text-[#A1A4AA] leading-relaxed">
                  Create your weekly class schedule directly inside Aurelia. The AI chatbot will use your SQLite timetable records to answer questions about upcoming lectures, faculty, rooms, and free slots.
                </p>
              </div>
              <div className="pt-2">
                <button
                  onClick={openCreateTimetableModal}
                  className="btn-bronze text-xs py-2.5 px-6 font-semibold flex items-center gap-2 mx-auto shadow-lg"
                >
                  <Plus size={16} />
                  <span>Create Timetable</span>
                </button>
              </div>
            </div>
          ) : (
            /* Timetable Exists */
            <div className="space-y-6">
              {/* Timetable Header Card */}
              <div className="card-dark p-5 rounded-2xl bg-[#121418] border border-white/10 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-bold text-white tracking-tight">{timetable?.name || 'Semester Timetable'}</h2>
                    {timetable?.academicYear && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[#C59A55]">
                        AY: {timetable.academicYear}
                      </span>
                    )}
                    {timetable?.semester && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white">
                        {timetable.semester}
                      </span>
                    )}
                    {timetable?.section && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[#42D6A4]">
                        Sec: {timetable.section}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#A1A4AA] font-mono">
                    {timetable?.periods?.length || 0} periods registered across {activeDays.length} active days
                  </p>
                </div>

                {/* Actions & View Switcher */}
                <div className="flex flex-wrap items-center gap-2.5">
                  {/* View Mode Buttons */}
                  <div className="flex items-center p-1 bg-[#08090B] border border-white/10 rounded-lg">
                    <button
                      onClick={() => setViewMode('grid')}
                      className={`p-1.5 rounded text-xs flex items-center gap-1.5 transition-all ${
                        viewMode === 'grid' ? 'bg-[#C59A55] text-black font-semibold' : 'text-[#A1A4AA] hover:text-white'
                      }`}
                      title="Weekly Grid View"
                    >
                      <Grid3X3 size={14} />
                      <span className="hidden sm:inline">Weekly Grid</span>
                    </button>
                    <button
                      onClick={() => setViewMode('day')}
                      className={`p-1.5 rounded text-xs flex items-center gap-1.5 transition-all ${
                        viewMode === 'day' ? 'bg-[#C59A55] text-black font-semibold' : 'text-[#A1A4AA] hover:text-white'
                      }`}
                      title="Daily Timeline View"
                    >
                      <Clock size={14} />
                      <span className="hidden sm:inline">Daily View</span>
                    </button>
                    <button
                      onClick={() => setViewMode('list')}
                      className={`p-1.5 rounded text-xs flex items-center gap-1.5 transition-all ${
                        viewMode === 'list' ? 'bg-[#C59A55] text-black font-semibold' : 'text-[#A1A4AA] hover:text-white'
                      }`}
                      title="List View"
                    >
                      <List size={14} />
                      <span className="hidden sm:inline">List View</span>
                    </button>
                  </div>

                  {/* Add Period */}
                  <button
                    onClick={openAddPeriodModal}
                    className="btn-secondary text-xs py-2 px-3 flex items-center gap-1.5"
                  >
                    <Plus size={14} />
                    <span>Add Period</span>
                  </button>

                  {/* Edit Timetable */}
                  <button
                    onClick={openEditTimetableModal}
                    className="btn-secondary text-xs py-2 px-3 flex items-center gap-1.5"
                  >
                    <Edit3 size={14} />
                    <span>Edit</span>
                  </button>

                  {/* Delete Timetable */}
                  <button
                    onClick={confirmDeleteTimetable}
                    className="p-2 rounded-lg bg-white/5 hover:bg-[#F07878]/15 border border-white/10 hover:border-[#F07878]/30 text-[#A1A4AA] hover:text-[#F07878] transition-colors"
                    title="Delete entire timetable"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>

              {/* VIEW 1: WEEKLY GRID VIEW */}
              {viewMode === 'grid' && (
                <div className="overflow-x-auto pb-4">
                  <div className={`grid gap-4 ${displayDaysGrid.length >= 7 ? 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-7 min-w-[950px]' : 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6 min-w-[850px]'}`}>
                    {displayDaysGrid.map(day => {
                      const dayClasses = periodsByDay[day] || [];
                      return (
                        <div key={day} className="card-dark rounded-xl bg-[#121418] border border-white/10 flex flex-col min-h-[360px] overflow-hidden">
                          {/* Day Header */}
                          <div className="p-3 bg-[#181B20] border-b border-white/5 flex items-center justify-between">
                            <span className="text-xs font-semibold text-white tracking-wide">{day}</span>
                            <span className="text-[10px] font-mono text-[#C59A55] bg-[#C59A55]/10 px-1.5 py-0.5 rounded border border-[#C59A55]/20">
                              {dayClasses.length}
                            </span>
                          </div>

                          {/* Periods in Day */}
                          <div className="p-2.5 flex-1 space-y-2.5">
                            {dayClasses.length === 0 ? (
                              <div className="h-full flex flex-col items-center justify-center p-6 text-center text-[#696E78]">
                                <Clock size={18} className="opacity-40 mb-1" />
                                <span className="text-[11px] font-mono">No classes</span>
                              </div>
                            ) : (
                              dayClasses.map((p, idx) => {
                                const pNum = p.periodNumber || p.period_number || (idx + 1);
                                return (
                                <div
                                  key={p.id}
                                  className="group p-3 rounded-lg bg-[#08090B] border border-white/5 hover:border-[#C59A55]/40 transition-all space-y-1.5 relative shadow-sm"
                                >
                                  <div className="flex items-start justify-between gap-1">
                                    <div className="flex items-center gap-1.5 min-w-0">
                                      <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/30 font-bold shrink-0">
                                        {getOrdinalLabel(pNum)}
                                      </span>
                                      <span className="text-xs font-semibold text-white leading-tight truncate">
                                        {p.subjectName}
                                      </span>
                                    </div>
                                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 shrink-0">
                                      <button
                                        onClick={() => openEditPeriodModal(p)}
                                        className="p-1 hover:text-[#C59A55] text-[#A1A4AA]"
                                        title="Edit period"
                                      >
                                        <Edit3 size={11} />
                                      </button>
                                      <button
                                        onClick={() => confirmDeletePeriod(p)}
                                        className="p-1 hover:text-[#F07878] text-[#A1A4AA]"
                                        title="Delete period"
                                      >
                                        <Trash2 size={11} />
                                      </button>
                                    </div>
                                  </div>

                                  {p.subjectCode && (
                                    <div className="text-[10px] font-mono text-[#C59A55]">{p.subjectCode}</div>
                                  )}

                                  <div className="text-[10px] font-mono text-[#A1A4AA] flex items-center gap-1">
                                    <Clock size={11} className="text-[#C59A55]" />
                                    <span>{p.startTime} – {p.endTime}</span>
                                  </div>

                                  {p.room && (
                                    <div className="text-[10px] font-mono text-[#ECEFF1] flex items-center gap-1">
                                      <MapPin size={11} className="text-blue-400" />
                                      <span>{p.room}</span>
                                    </div>
                                  )}

                                  {p.faculty && (
                                    <div className="text-[10px] text-[#A1A4AA] flex items-center gap-1">
                                      <UserIcon size={11} className="text-purple-400" />
                                      <span className="truncate">{p.faculty}</span>
                                    </div>
                                  )}

                                  <div className="pt-1 flex items-center justify-between">
                                    <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-white/5 text-[#E6C17A] border border-white/5">
                                      {p.classType || 'Lecture'}
                                    </span>
                                    {p.notes && (
                                      <span className="text-[9px] text-[#696E78] truncate max-w-[90px]" title={p.notes}>
                                        {p.notes}
                                      </span>
                                    )}
                                  </div>
                                </div>
                                );
                              })
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* VIEW 2: DAILY VIEW */}
              {viewMode === 'day' && (
                <div className="space-y-4">
                  {/* Day Selector Pills */}
                  <div className="flex flex-wrap gap-2">
                    {displayDaysGrid.map(day => {
                      const count = periodsByDay[day]?.length || 0;
                      return (
                        <button
                          key={day}
                          onClick={() => setSelectedDay(day)}
                          className={`px-4 py-2 rounded-xl text-xs font-medium flex items-center gap-2 border transition-all ${
                            selectedDay === day
                              ? 'bg-[#C59A55] text-black border-[#C59A55] font-semibold shadow-md'
                              : 'bg-[#121418] text-[#A1A4AA] border-white/10 hover:border-white/20 hover:text-white'
                          }`}
                        >
                          <span>{day}</span>
                          <span className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${
                            selectedDay === day ? 'bg-black/20 text-black' : 'bg-white/5 text-[#C59A55]'
                          }`}>
                            {count}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {/* Selected Day Timeline */}
                  <div className="card-dark p-6 rounded-2xl bg-[#121418] border border-white/10 space-y-4">
                    <div className="flex items-center justify-between pb-3 border-b border-white/5">
                      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                        <Clock size={16} className="text-[#C59A55]" />
                        <span>Schedule for {selectedDay} ({periodsByDay[selectedDay]?.length || 0} classes)</span>
                      </h3>
                      <button
                        onClick={openAddPeriodModal}
                        className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5"
                      >
                        <Plus size={13} />
                        <span>Add Class on {selectedDay}</span>
                      </button>
                    </div>

                    {(periodsByDay[selectedDay]?.length || 0) === 0 ? (
                      <div className="p-12 text-center text-xs text-[#696E78] space-y-1">
                        <p className="text-white font-medium">No classes scheduled on {selectedDay}.</p>
                        <p className="text-[#A1A4AA]">Your whole day is free! You can add an optional study block or lecture above.</p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {(periodsByDay[selectedDay] || []).map((p, idx) => {
                          const pNum = p.periodNumber || p.period_number || (idx + 1);
                          return (
                          <div
                            key={p.id}
                            className="p-4 rounded-xl bg-[#08090B] border border-white/5 hover:border-[#C59A55]/30 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                          >
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/40 font-bold">
                                  {getOrdinalLabel(pNum)} Period
                                </span>
                                <span className="text-sm font-bold text-white">{p.subjectName}</span>
                                {p.subjectCode && (
                                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#C59A55]/15 text-[#E6C17A] border border-[#C59A55]/30">
                                    {p.subjectCode}
                                  </span>
                                )}
                                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-[#A1A4AA] border border-white/10">
                                  {p.classType || 'Lecture'}
                                </span>
                              </div>
                              <div className="flex flex-wrap items-center gap-4 text-xs text-[#A1A4AA]">
                                <span className="flex items-center gap-1 text-[#42D6A4] font-mono">
                                  <Clock size={13} />
                                  <span>{p.startTime} – {p.endTime}</span>
                                </span>
                                {p.room && (
                                  <span className="flex items-center gap-1 text-white font-mono">
                                    <MapPin size={13} className="text-blue-400" />
                                    <span>Room: {p.room}</span>
                                  </span>
                                )}
                                {p.faculty && (
                                  <span className="flex items-center gap-1 text-white">
                                    <UserIcon size={13} className="text-purple-400" />
                                    <span>Faculty: {p.faculty}</span>
                                  </span>
                                )}
                              </div>
                              {p.notes && (
                                <p className="text-[11px] text-[#696E78] italic pt-1">{p.notes}</p>
                              )}
                            </div>

                            <div className="flex items-center gap-2 self-end md:self-auto">
                              <button
                                onClick={() => openEditPeriodModal(p)}
                                className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1"
                              >
                                <Edit3 size={12} />
                                <span>Edit</span>
                              </button>
                              <button
                                onClick={() => confirmDeletePeriod(p)}
                                className="p-2 rounded-lg bg-white/5 hover:bg-[#F07878]/15 text-[#A1A4AA] hover:text-[#F07878] transition-colors"
                                title="Delete"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* VIEW 3: LIST VIEW */}
              {viewMode === 'list' && (
                <div className="card-dark rounded-2xl bg-[#121418] border border-white/10 overflow-hidden shadow-xl">
                  <table className="w-full text-left text-xs text-[#A1A4AA]">
                    <thead className="bg-[#08090B] border-b border-white/5 font-mono text-[10px] uppercase text-[#696E78]">
                      <tr>
                        <th className="p-3.5 pl-5">Day</th>
                        <th className="p-3.5">Period</th>
                        <th className="p-3.5">Time</th>
                        <th className="p-3.5">Subject</th>
                        <th className="p-3.5">Code</th>
                        <th className="p-3.5">Room</th>
                        <th className="p-3.5">Faculty</th>
                        <th className="p-3.5">Type</th>
                        <th className="p-3.5">Notes</th>
                        <th className="p-3.5 pr-5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {displayDaysGrid.map(day => {
                        const dayPeriods = periodsByDay[day] || [];
                        return dayPeriods.map((p, idx) => {
                          const pNum = p.periodNumber || p.period_number || (idx + 1);
                          return (
                          <tr key={p.id} className="hover:bg-white/[0.02] transition-colors">
                            <td className="p-3.5 pl-5 font-mono font-semibold text-white">{p.dayOfWeek || day}</td>
                            <td className="p-3.5 font-mono text-[10px] text-[#E6C17A] font-semibold whitespace-nowrap">
                              {getOrdinalLabel(pNum)}
                            </td>
                            <td className="p-3.5 font-mono text-[#42D6A4] whitespace-nowrap">{p.startTime} – {p.endTime}</td>
                            <td className="p-3.5 font-medium text-white">{p.subjectName}</td>
                            <td className="p-3.5 font-mono text-[#C59A55]">{p.subjectCode || '—'}</td>
                            <td className="p-3.5 font-mono text-white">{p.room || '—'}</td>
                            <td className="p-3.5">{p.faculty || '—'}</td>
                            <td className="p-3.5 font-mono uppercase text-[10px] text-[#E6C17A]">{p.classType || 'Lecture'}</td>
                            <td className="p-3.5 text-[11px] text-[#696E78] truncate max-w-xs">{p.notes || '—'}</td>
                            <td className="p-3.5 pr-5 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => openEditPeriodModal(p)}
                                  className="p-1.5 rounded hover:bg-white/10 text-[#A1A4AA] hover:text-[#C59A55]"
                                  title="Edit period"
                                >
                                  <Edit3 size={13} />
                                </button>
                                <button
                                  onClick={() => confirmDeletePeriod(p)}
                                  className="p-1.5 rounded hover:bg-[#F07878]/10 text-[#A1A4AA] hover:text-[#F07878]"
                                  title="Delete period"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            </td>
                          </tr>
                          );
                        });
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: LEARNING DOCUMENTS & RAG */}
      {/* ========================================================================= */}
      {activeTab === 'rag' && (
        <div className="space-y-6">
          {/* Upload Zone */}
          <div className="card-dark p-6 rounded-2xl bg-[#121418] border border-white/10 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="text-xs font-mono uppercase text-[#E6C17A] flex items-center gap-2">
                <UploadCloud size={16} />
                <span>Knowledge Document Vector Ingestion</span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[#696E78] font-mono">Category:</span>
                <select
                  value={docTypeSelection}
                  onChange={(e) => setDocTypeSelection(e.target.value)}
                  className="bg-[#08090B] border border-white/10 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                >
                  <option value="SYLLABUS">Course Syllabus (Grounded RAG)</option>
                  <option value="APPROVED_SYLLABUS">Approved Syllabus (Grounded RAG)</option>
                  <option value="NOTES">Lecture Notes (Grounded RAG)</option>
                  <option value="TEXTBOOK">Textbook / Learning PDF (Grounded RAG)</option>
                </select>
              </div>
            </div>

            <label className="border-2 border-dashed border-white/10 hover:border-[#C59A55]/50 rounded-xl p-8 text-center cursor-pointer transition-colors block bg-[#08090B]">
              <input
                type="file"
                onChange={handleFileUpload}
                disabled={uploading}
                className="hidden"
                accept=".pdf,.txt,.md,.csv,.json"
              />
              {uploading ? (
                <div className="space-y-2">
                  <Loader2 size={32} className="mx-auto text-[#C59A55] animate-spin" />
                  <div className="text-xs text-white font-medium">
                    Extracting text, chunking, and calculating vector embeddings...
                  </div>
                  <div className="text-[11px] text-[#696E78] font-mono">Preserving document structure and page citations</div>
                </div>
              ) : (
                <div className="space-y-1">
                  <UploadCloud size={32} className="mx-auto text-[#C59A55] mb-2" />
                  <div className="text-xs font-semibold text-white">
                    Drag &amp; drop {docTypeSelection.toLowerCase().replace('_', ' ')} PDF here, or click to browse
                  </div>
                  <div className="text-[10px] text-[#696E78]">
                    Supports PDF, TXT, CSV up to 25MB with automatic semantic indexing
                  </div>
                </div>
              )}
            </label>
          </div>

          {/* RAG Query Tester */}
          <div className="card-dark p-6 rounded-2xl bg-[#121418] border border-white/10 space-y-4">
            <div className="text-xs font-mono uppercase text-[#42D6A4] flex items-center gap-2">
              <Sparkles size={14} />
              <span>Semantic Vector Search &amp; Grounding Test</span>
            </div>

            <form onSubmit={handleSearch} className="flex gap-2">
              <input
                type="text"
                placeholder="Ask a question about your uploaded documents (e.g. 'What topics are covered in Unit 3 of the syllabus?')..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#C59A55]"
              />
              <button
                type="submit"
                disabled={!searchQuery.trim() || querying}
                className="btn-bronze text-xs py-2 px-5 whitespace-nowrap"
              >
                {querying ? <Loader2 size={14} className="animate-spin" /> : <span>Retrieve Fact</span>}
              </button>
            </form>

            {queryResult && (
              <div className="p-4 rounded-xl bg-[#08090B] border border-white/10 space-y-4 animate-in fade-in">
                <div className="space-y-1.5">
                  <div className="text-[10px] font-mono uppercase text-[#C59A55] font-semibold tracking-wider flex items-center gap-1.5">
                    <Sparkles size={12} className="text-[#E6C17A]" />
                    <span>Direct Answer</span>
                  </div>
                  <p className="text-xs sm:text-sm text-[#F5F3EE] leading-relaxed whitespace-pre-wrap">
                    {queryResult.answer?.startsWith('**Answer:**')
                      ? queryResult.answer.split('**Grounded Evidentiary Sources:**')[0].replace('**Answer:**', '').trim()
                      : queryResult.answer?.split('**Grounded Evidentiary Sources:**')[0].trim()}
                  </p>
                </div>

                {queryResult.sources && queryResult.sources.length > 0 && (
                  <div className="pt-3 border-t border-white/10 space-y-2.5">
                    <div className="text-[11px] font-mono uppercase text-[#A1A4AA] flex items-center gap-1.5 font-semibold">
                      <ShieldCheck size={13} className="text-[#42D6A4]" />
                      <span className="text-white">Grounded Evidentiary Sources:</span>
                    </div>
                    <div className="space-y-2">
                      {queryResult.sources.map((s, idx) => (
                        <div key={idx} className="p-3 rounded-xl bg-[#121418] border border-white/10 space-y-1.5 text-xs shadow-sm">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-semibold text-white flex items-center gap-1.5">
                              <FileText size={13} className="text-[#C59A55]" />
                              <span>{s.title}</span>
                              <span className="text-[10px] text-[#A1A4AA] font-mono bg-white/5 px-1.5 py-0.5 rounded border border-white/5">
                                {s.page ? `Page ${s.page}` : 'Page unavailable'}
                              </span>
                            </div>
                          </div>
                          {s.snippet && (
                            <blockquote className="border-l-2 border-[#C59A55] pl-3 py-1 bg-white/[0.02] rounded-r text-[11px] font-serif text-[#ECEFF1] italic leading-relaxed">
                              &quot;{s.snippet}&quot;
                            </blockquote>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Indexed Documents Table */}
          <div className="space-y-4">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <FileText size={16} className="text-[#C59A55]" />
              <span>Uploaded Learning Documents ({documents.length})</span>
            </h2>

            {documents.length === 0 ? (
              <div className="p-8 text-center text-xs text-[#696E78] card-dark rounded-2xl bg-[#121418] border border-white/10">
                No learning documents indexed yet. Upload course syllabi or notes above.
              </div>
            ) : (
              <div className="card-dark rounded-2xl bg-[#121418] border border-white/10 overflow-hidden shadow-xl">
                <table className="w-full text-left text-xs text-[#A1A4AA]">
                  <thead className="bg-[#08090B] border-b border-white/5 font-mono text-[10px] uppercase text-[#696E78]">
                    <tr>
                      <th className="p-3.5 pl-5">Document Name</th>
                      <th className="p-3.5">Category</th>
                      <th className="p-3.5">Status</th>
                      <th className="p-3.5">Chunks Vectorized</th>
                      <th className="p-3.5">Uploaded Date</th>
                      <th className="p-3.5 pr-5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {documents.map((doc) => (
                      <tr key={doc.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="p-3.5 pl-5 font-medium text-white flex items-center gap-2">
                          <FileText size={14} className="text-[#C59A55]" />
                          <span>{doc.filename}</span>
                        </td>
                        <td className="p-3.5 font-mono text-[11px]">
                          <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[#E6C17A] uppercase">
                            {doc.category || doc.documentType}
                          </span>
                        </td>
                        <td className="p-3.5 font-mono text-[11px]">
                          {(() => {
                            const rawStatus = (doc.status || doc.processingStatus || 'INDEXED').toUpperCase();
                            if (rawStatus === 'INDEXED' || rawStatus === 'COMPLETED') {
                              return (
                                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#42D6A4]/10 border border-[#42D6A4]/30 text-[#42D6A4] text-[10px] font-semibold tracking-wide">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#42D6A4]" />
                                  INDEXED
                                </span>
                              );
                            }
                            if (rawStatus === 'PROCESSING') {
                              return (
                                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#E6C17A]/10 border border-[#E6C17A]/30 text-[#E6C17A] text-[10px] font-semibold tracking-wide">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#E6C17A] animate-pulse" />
                                  PROCESSING
                                </span>
                              );
                            }
                            return (
                              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#F07878]/10 border border-[#F07878]/30 text-[#F07878] text-[10px] font-semibold tracking-wide">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#F07878]" />
                                FAILED
                              </span>
                            );
                          })()}
                        </td>
                        <td className="p-3.5 font-mono text-[11px] text-[#42D6A4]">
                          {doc.chunkCount || 0} chunks
                        </td>
                        <td className="p-3.5 font-mono text-[11px]">
                          {new Date(doc.uploadedAt || doc.createdAt).toLocaleDateString()}
                        </td>
                        <td className="p-3.5 pr-5 text-right">
                          <button
                            onClick={() => handleDeleteDocument(doc.id)}
                            className="p-1.5 rounded hover:bg-[#F07878]/10 text-[#696E78] hover:text-[#F07878] transition-colors"
                            title="Delete document and vectorized chunks"
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TIMETABLE EDITOR MODAL (Full Creation / Edit) */}
      {/* ========================================================================= */}
      {editorModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="card-dark w-full max-w-4xl max-h-[90vh] bg-[#121418] border border-[#C59A55]/40 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="p-5 border-b border-white/10 flex items-center justify-between bg-[#181B20]">
              <div className="space-y-0.5">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Calendar size={18} className="text-[#C59A55]" />
                  <span>{editorModal.mode === 'create' ? 'Create Academic Timetable' : 'Edit Academic Timetable'}</span>
                </h3>
                <p className="text-[11px] text-[#A1A4AA]">
                  Configure your weekly periods. Time conflicts will be highlighted automatically.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditorModal(prev => ({ ...prev, isOpen: false }))}
                className="p-1 text-[#A1A4AA] hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-5 flex-1">
              {editorModal.error && (
                <div className="p-3 rounded-lg bg-[#F07878]/15 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center gap-2">
                  <AlertCircle size={15} />
                  <span>{editorModal.error}</span>
                </div>
              )}

              {/* Overlaps Warning Banner */}
              {editorOverlaps.length > 0 && (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 space-y-1">
                  <div className="font-semibold flex items-center gap-1.5 text-amber-200">
                    <AlertTriangle size={14} />
                    <span>Overlapping Periods Detected ({editorOverlaps.length})</span>
                  </div>
                  <div className="space-y-0.5 text-[11px] font-mono">
                    {editorOverlaps.map((ov, i) => (
                      <div key={i}>{ov.message}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Timetable Metadata Form */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-4 rounded-xl bg-[#08090B] border border-white/5">
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Timetable Name *</label>
                  <input
                    type="text"
                    value={editorModal.name}
                    onChange={(e) => setEditorModal(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g. Fall 2026 Schedule"
                    className="w-full bg-[#121418] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Academic Year</label>
                  <input
                    type="text"
                    value={editorModal.academicYear}
                    onChange={(e) => setEditorModal(prev => ({ ...prev, academicYear: e.target.value }))}
                    placeholder="e.g. 2026-2027"
                    className="w-full bg-[#121418] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Semester</label>
                  <input
                    type="text"
                    value={editorModal.semester}
                    onChange={(e) => setEditorModal(prev => ({ ...prev, semester: e.target.value }))}
                    placeholder="e.g. Semester 5"
                    className="w-full bg-[#121418] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Section</label>
                  <input
                    type="text"
                    value={editorModal.section}
                    onChange={(e) => setEditorModal(prev => ({ ...prev, section: e.target.value }))}
                    placeholder="e.g. Section A"
                    className="w-full bg-[#121418] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
              </div>

              {/* Dynamic Periods List */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
                    Weekly Periods ({editorModal.periods.length})
                  </h4>
                  <button
                    type="button"
                    onClick={handleEditorAddPeriod}
                    className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1"
                  >
                    <Plus size={13} />
                    <span>Add Period</span>
                  </button>
                </div>

                <div className="space-y-2.5">
                  {editorModal.periods.map((p, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-[#08090B] border border-white/10 space-y-2"
                    >
                      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
                        {/* Day */}
                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Day</label>
                          <select
                            value={p.day_of_week}
                            onChange={(e) => handleEditorPeriodChange(idx, 'day_of_week', e.target.value)}
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white"
                          >
                            {DAYS_OF_WEEK.map(d => (
                              <option key={d} value={d}>{d}</option>
                            ))}
                          </select>
                        </div>

                        {/* Subject */}
                        <div className="sm:col-span-2">
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Subject Name *</label>
                          <input
                            type="text"
                            value={p.subject_name}
                            onChange={(e) => handleEditorPeriodChange(idx, 'subject_name', e.target.value)}
                            placeholder="e.g. Java Programming"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white"
                          />
                        </div>

                        {/* Subject Code */}
                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Code</label>
                          <input
                            type="text"
                            value={p.subject_code}
                            onChange={(e) => handleEditorPeriodChange(idx, 'subject_code', e.target.value)}
                            placeholder="CS301"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white font-mono"
                          />
                        </div>

                        {/* Start Time */}
                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Start Time *</label>
                          <input
                            type="text"
                            value={p.start_time}
                            onChange={(e) => handleEditorPeriodChange(idx, 'start_time', e.target.value)}
                            placeholder="09:00"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white font-mono"
                          />
                        </div>

                        {/* End Time */}
                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">End Time *</label>
                          <input
                            type="text"
                            value={p.end_time}
                            onChange={(e) => handleEditorPeriodChange(idx, 'end_time', e.target.value)}
                            placeholder="10:00"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white font-mono"
                          />
                        </div>
                      </div>

                      {/* Row 2: Room, Faculty, Class Type, Notes, Delete */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 pt-1">
                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Room</label>
                          <input
                            type="text"
                            value={p.room}
                            onChange={(e) => handleEditorPeriodChange(idx, 'room', e.target.value)}
                            placeholder="LH-101"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white"
                          />
                        </div>

                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Faculty</label>
                          <input
                            type="text"
                            value={p.faculty}
                            onChange={(e) => handleEditorPeriodChange(idx, 'faculty', e.target.value)}
                            placeholder="Dr. Alan"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white"
                          />
                        </div>

                        <div>
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Type</label>
                          <select
                            value={p.class_type}
                            onChange={(e) => handleEditorPeriodChange(idx, 'class_type', e.target.value)}
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white"
                          >
                            {CLASS_TYPES.map(t => (
                              <option key={t} value={t}>{t}</option>
                            ))}
                          </select>
                        </div>

                        <div className="sm:col-span-2">
                          <label className="text-[10px] font-mono text-[#696E78] block mb-0.5">Notes</label>
                          <input
                            type="text"
                            value={p.notes}
                            onChange={(e) => handleEditorPeriodChange(idx, 'notes', e.target.value)}
                            placeholder="Optional notes"
                            className="w-full bg-[#121418] border border-white/10 rounded px-2 py-1 text-xs text-white"
                          />
                        </div>

                        <div className="flex items-end justify-end">
                          <button
                            type="button"
                            onClick={() => handleEditorRemovePeriod(idx)}
                            className="p-1.5 rounded hover:bg-[#F07878]/15 text-[#A1A4AA] hover:text-[#F07878] transition-colors flex items-center gap-1 text-xs"
                          >
                            <Trash2 size={13} />
                            <span className="sm:hidden">Remove</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-white/10 bg-[#181B20] flex items-center justify-between">
              <span className="text-xs text-[#A1A4AA] font-mono">
                {editorModal.periods.length} total periods
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setEditorModal(prev => ({ ...prev, isOpen: false }))}
                  className="btn-secondary text-xs py-2 px-4"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={editorModal.submitting}
                  onClick={handleSaveTimetable}
                  className="btn-bronze text-xs py-2 px-5 flex items-center gap-1.5"
                >
                  {editorModal.submitting ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                  <span>Save Timetable</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SINGLE PERIOD MODAL (Quick Add / Edit) */}
      {/* ========================================================================= */}
      {periodModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="card-dark w-full max-w-lg bg-[#121418] border border-[#C59A55]/40 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-white/10 flex items-center justify-between bg-[#181B20]">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Clock size={16} className="text-[#C59A55]" />
                <span>{periodModal.mode === 'add' ? 'Add Period' : 'Edit Period'}</span>
              </h3>
              <button
                type="button"
                onClick={() => setPeriodModal(prev => ({ ...prev, isOpen: false }))}
                className="p-1 text-[#A1A4AA] hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-3.5">
              {periodModal.error && (
                <div className="p-3 rounded-lg bg-[#F07878]/15 border border-[#F07878]/30 text-xs text-[#F07878]">
                  {periodModal.error}
                </div>
              )}

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Day of Week *</label>
                  <select
                    value={periodModal.dayOfWeek}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, dayOfWeek: e.target.value }))}
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                  >
                    {DAYS_OF_WEEK.map(d => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Class Type</label>
                  <select
                    value={periodModal.classType}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, classType: e.target.value }))}
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                  >
                    {CLASS_TYPES.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Period # (Opt)</label>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={periodModal.periodNumber || ''}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, periodNumber: e.target.value }))}
                    placeholder="Auto"
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Subject Name *</label>
                <input
                  type="text"
                  value={periodModal.subjectName}
                  onChange={(e) => setPeriodModal(prev => ({ ...prev, subjectName: e.target.value }))}
                  placeholder="e.g. Database Management Systems"
                  className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Subject Code</label>
                  <input
                    type="text"
                    value={periodModal.subjectCode}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, subjectCode: e.target.value }))}
                    placeholder="CS304"
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white font-mono"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Start Time *</label>
                  <input
                    type="text"
                    value={periodModal.startTime}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, startTime: e.target.value }))}
                    placeholder="09:00"
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white font-mono"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">End Time *</label>
                  <input
                    type="text"
                    value={periodModal.endTime}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, endTime: e.target.value }))}
                    placeholder="10:00"
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Room / Lab</label>
                  <input
                    type="text"
                    value={periodModal.room}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, room: e.target.value }))}
                    placeholder="Lab 2 / LH-101"
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Faculty / Instructor</label>
                  <input
                    type="text"
                    value={periodModal.faculty}
                    onChange={(e) => setPeriodModal(prev => ({ ...prev, faculty: e.target.value }))}
                    placeholder="Dr. Sharma"
                    className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-mono text-[#A1A4AA] block mb-1">Notes</label>
                <input
                  type="text"
                  value={periodModal.notes}
                  onChange={(e) => setPeriodModal(prev => ({ ...prev, notes: e.target.value }))}
                  placeholder="Optional classroom instructions or notes"
                  className="w-full bg-[#08090B] border border-white/10 rounded px-2.5 py-1.5 text-xs text-white"
                />
              </div>
            </div>

            <div className="p-4 border-t border-white/10 bg-[#181B20] flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setPeriodModal(prev => ({ ...prev, isOpen: false }))}
                className="btn-secondary text-xs py-2 px-4"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={periodModal.submitting}
                onClick={handleSavePeriod}
                className="btn-bronze text-xs py-2 px-5 flex items-center gap-1.5"
              >
                {periodModal.submitting ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                <span>{periodModal.mode === 'add' ? 'Add Period' : 'Save Changes'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* DELETE CONFIRMATION MODAL */}
      {/* ========================================================================= */}
      {deleteConfirm.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="card-dark w-full max-w-sm bg-[#121418] border border-[#F07878]/30 rounded-2xl p-5 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-[#F07878]">
              <div className="p-2.5 rounded-xl bg-[#F07878]/10 border border-[#F07878]/20">
                <Trash2 size={20} />
              </div>
              <h3 className="text-sm font-bold text-white">
                {deleteConfirm.type === 'timetable' ? 'Delete Timetable?' : 'Delete Period?'}
              </h3>
            </div>

            <p className="text-xs text-[#A1A4AA] leading-relaxed">
              Are you sure you want to delete <span className="text-white font-semibold">&quot;{deleteConfirm.name}&quot;</span>? This will permanently remove the record from your SQLite database.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDeleteConfirm({ isOpen: false, type: null, id: null, periodId: null, name: '' })}
                className="btn-secondary text-xs py-2 px-4"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={executeDelete}
                className="px-4 py-2 rounded-lg bg-[#F07878] hover:bg-[#F07878]/90 text-white font-medium text-xs transition-colors"
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
