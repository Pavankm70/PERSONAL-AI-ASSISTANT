/**
 * Aurelia AI — Global Timezone & Date Consistency Utilities
 * Provides standardized, timezone-aware date/time calculations and formatting
 * across Overview, Calendar, Inbox, Plans, and Assistant Chat.
 */

/**
 * Returns the effective user timezone, defaulting to Intl browser timezone or UTC.
 */
export function getEffectiveTimezone(userTimezone) {
  if (userTimezone && typeof userTimezone === 'string' && userTimezone.trim()) {
    try {
      // Validate that Intl supports this timezone
      Intl.DateTimeFormat(undefined, { timeZone: userTimezone });
      return userTimezone.trim();
    } catch (e) {
      // Fallback below
    }
  }
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch (e) {
    return 'UTC';
  }
}

/**
 * Formats the current date in the user's timezone as "YYYY-MM-DD".
 */
export function getCurrentUserDate(userTimezone) {
  const tz = getEffectiveTimezone(userTimezone);
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return formatter.format(now); // en-CA gives YYYY-MM-DD
}

/**
 * Formats the current time in the user's timezone as "HH:mm".
 */
export function getCurrentUserTime(userTimezone) {
  const tz = getEffectiveTimezone(userTimezone);
  const now = new Date();
  return now.toLocaleTimeString([], {
    timeZone: tz,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/**
 * Calculates a timezone-accurate greeting based on the user's local clock hour.
 * Morning:   5:00 AM – 11:59 AM
 * Afternoon: 12:00 PM – 4:59 PM
 * Evening:   5:00 PM – 8:59 PM
 * Night:     9:00 PM – 4:59 AM
 */
export function getTimezoneGreeting(userTimezone) {
  const tz = getEffectiveTimezone(userTimezone);
  try {
    const now = new Date();
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: 'numeric',
      hour12: false,
    });
    const hour = parseInt(formatter.format(now), 10);
    if (hour >= 5 && hour < 12) return 'Good morning';
    if (hour >= 12 && hour < 17) return 'Good afternoon';
    if (hour >= 17 && hour < 21) return 'Good evening';
    return 'Good night';
  } catch (e) {
    const clientHour = new Date().getHours();
    if (clientHour >= 5 && clientHour < 12) return 'Good morning';
    if (clientHour >= 12 && clientHour < 17) return 'Good afternoon';
    if (clientHour >= 17 && clientHour < 21) return 'Good evening';
    return 'Good night';
  }
}

/**
 * Converts any timestamp or date input into a Date object representing
 * the moment in time, with safe parsing of local date-only strings ("YYYY-MM-DD").
 */
export function parseDateSafe(dateOrIso) {
  if (!dateOrIso) return null;
  if (dateOrIso instanceof Date) return isNaN(dateOrIso.getTime()) ? null : dateOrIso;

  if (typeof dateOrIso === 'string') {
    const trimmed = dateOrIso.trim();
    // Handle pure date string YYYY-MM-DD without time
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
      const [y, m, d] = trimmed.split('-').map(Number);
      return new Date(y, m - 1, d, 12, 0, 0); // Noon local avoids edge transitions
    }
    const parsed = new Date(trimmed);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  if (typeof dateOrIso === 'number') {
    const parsed = new Date(dateOrIso);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  return null;
}

/**
 * Converts a date/ISO string to an ISO string anchored in the user's timezone.
 */
export function convertToUserTimezone(dateOrIso, userTimezone) {
  const d = parseDateSafe(dateOrIso);
  if (!d) return null;
  const tz = getEffectiveTimezone(userTimezone);
  return d.toLocaleString('en-US', { timeZone: tz });
}

/**
 * Returns a Date object for 00:00:00.000 of the specified date in the user's timezone.
 */
export function getStartOfDay(dateOrIso, userTimezone) {
  const tz = getEffectiveTimezone(userTimezone);
  const d = parseDateSafe(dateOrIso) || new Date();
  
  // Format parts in user's timezone
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  });
  const parts = formatter.formatToParts(d);
  const partMap = {};
  for (const p of parts) partMap[p.type] = p.value;

  const y = Number(partMap.year);
  const m = Number(partMap.month) - 1;
  const day = Number(partMap.day);

  return new Date(y, m, day, 0, 0, 0, 0);
}

/**
 * Returns a Date object for 23:59:59.999 of the specified date in the user's timezone.
 */
export function getEndOfDay(dateOrIso, userTimezone) {
  const start = getStartOfDay(dateOrIso, userTimezone);
  return new Date(start.getTime() + 86400000 - 1);
}

/**
 * Returns the week start and end dates in the user's timezone.
 * weekStartsOn: 1 = Monday (default), 0 = Sunday.
 */
export function getWeekRange(dateOrIso, userTimezone, weekStartsOn = 1) {
  const startOfDay = getStartOfDay(dateOrIso, userTimezone);
  const dayOfWeek = startOfDay.getDay(); // 0 = Sunday, 1 = Monday, ...
  
  let diff = dayOfWeek - weekStartsOn;
  if (diff < 0) diff += 7;

  const weekStart = new Date(startOfDay.getTime() - diff * 86400000);
  const weekEnd = new Date(weekStart.getTime() + 7 * 86400000 - 1);

  return {
    start: weekStart,
    end: weekEnd,
    startDateStr: formatYearMonthDay(weekStart),
    endDateStr: formatYearMonthDay(weekEnd),
  };
}

/**
 * Returns the month start and end dates in the user's timezone.
 */
export function getMonthRange(dateOrIso, userTimezone) {
  const startOfDay = getStartOfDay(dateOrIso, userTimezone);
  const year = startOfDay.getFullYear();
  const month = startOfDay.getMonth();

  const monthStart = new Date(year, month, 1, 0, 0, 0, 0);
  const nextMonthStart = new Date(year, month + 1, 1, 0, 0, 0, 0);
  const monthEnd = new Date(nextMonthStart.getTime() - 1);

  return {
    start: monthStart,
    end: monthEnd,
    startDateStr: formatYearMonthDay(monthStart),
    endDateStr: formatYearMonthDay(monthEnd),
  };
}

/**
 * Helper to produce "YYYY-MM-DD" from local Date without UTC offset shift.
 */
export function formatYearMonthDay(dateObj) {
  if (!dateObj) return '';
  const y = dateObj.getFullYear();
  const m = String(dateObj.getMonth() + 1).padStart(2, '0');
  const d = String(dateObj.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * Formats a date for display (e.g. "Oct 30, 2026" or "Friday, October 30").
 */
export function formatDateForDisplay(dateOrIso, userTimezone, style = 'medium') {
  const d = parseDateSafe(dateOrIso);
  if (!d) return '';
  const tz = getEffectiveTimezone(userTimezone);

  if (style === 'short') {
    return d.toLocaleDateString([], { timeZone: tz, month: 'short', day: 'numeric' });
  }
  if (style === 'long') {
    return d.toLocaleDateString([], { timeZone: tz, weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  }
  if (style === 'weekday_short') {
    return d.toLocaleDateString([], { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric' });
  }
  // Default 'medium'
  return d.toLocaleDateString([], { timeZone: tz, month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Formats time range "10:00 AM – 11:30 AM" or "All-Day Event" in the user's timezone.
 */
export function formatTimeRange(startTime, endTime, userTimezone, isAllDay = false) {
  if (isAllDay || (!startTime?.includes('T') && !startTime?.includes(':'))) {
    return 'All-Day Event';
  }
  const tz = getEffectiveTimezone(userTimezone);
  try {
    const dStart = parseDateSafe(startTime);
    if (!dStart) return startTime || 'Scheduled';

    const startStr = dStart.toLocaleTimeString([], {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
    });

    if (endTime) {
      const dEnd = parseDateSafe(endTime);
      if (dEnd) {
        const endStr = dEnd.toLocaleTimeString([], {
          timeZone: tz,
          hour: '2-digit',
          minute: '2-digit',
        });
        return `${startStr} – ${endStr}`;
      }
    }
    return startStr;
  } catch (e) {
    return startTime || 'Scheduled';
  }
}

/**
 * Determines if two dates fall on the exact same calendar day in the user's timezone.
 */
export function isSameDay(date1, date2, userTimezone) {
  const d1 = parseDateSafe(date1);
  const d2 = parseDateSafe(date2);
  if (!d1 || !d2) return false;

  const tz = getEffectiveTimezone(userTimezone);
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return fmt.format(d1) === fmt.format(d2);
}

/**
 * Checks if a given date falls on "today" in the user's timezone.
 */
export function isToday(dateOrIso, userTimezone) {
  return isSameDay(dateOrIso, new Date(), userTimezone);
}

