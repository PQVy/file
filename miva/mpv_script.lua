local msg_text = ""
local enabled = true
local timer = nil  -- Biến để lưu trữ timer
local msg_duration = 5 -- Lưu thời lượng hiển thị (giây)

local text_color = "FFFFFF"
local bg_color   = "0000FF"
local font_name  = "Montserrat ExtraBold"
local font_size  = 100

local overlay = mp.create_osd_overlay("ass-events")
-- Khai báo độ phân giải cố định để tính tọa độ di chuyển chuẩn xác
overlay.res_x = 1920
overlay.res_y = 1080

local function update_overlay()
    if not enabled or msg_text == "" then
        overlay.data = ""
        overlay:update()
        return
    end

    local duration_ms = math.floor(msg_duration * 1000)

    -- Ước tính chiều rộng dòng chữ (số ký tự * cỡ chữ * hệ số co giãn)
    -- Đảm bảo khoảng cách tối thiểu là 800px để chữ ngắn không bị chạy quá nhanh
    local estimated_text_width = math.max(#msg_text * (font_size * 0.6), 800)

    -- Tọa độ bắt đầu (ngoài mép trái) và kết thúc (ngoài mép phải)
    local start_x = math.floor(-estimated_text_width)
    local end_x   = math.floor(1920 + estimated_text_width)

    local ass = string.format(
        "{\\an5}{\\move(%d, 540, %d, 540, 0, %d)}{\\fs%d}{\\fn%s}{\\b1}{\\1c&H%s&}{\\3a&HFF&}{\\bord0}{\\shad0}{\\bgc&H%s&}{\\ybord10}{\\xbord20}{\\fscx100}{\\fscy100}%s",
        start_x, end_x,
        duration_ms,
        font_size, font_name,
        text_color,
        bg_color,
        msg_text:gsub("\\n", "\\N")
    )

    overlay.data = ass
    overlay:update()
end

-- Hàm để xóa nội dung và dừng timer
local function clear_overlay()
    if timer then
        timer:kill()
        timer = nil
    end
    msg_text = ""
    update_overlay()
end

mp.register_script_message("show-text", function(text, duration)
    -- 1. Xóa bỏ timer cũ nếu đang chạy để tránh xung đột
    if timer then
        timer:kill()
    end

    msg_text = text or ""
    msg_duration = tonumber(duration) or 5
    enabled = true
    update_overlay()

    -- 2. Tạo timer mới và lưu vào biến 'timer'
    timer = mp.add_timeout(msg_duration, function()
        clear_overlay()
    end)
end)

mp.register_script_message("hide", function()
    clear_overlay()
end)

-- Các hàm set property
mp.register_script_message("set-font", function(name)
    font_name = name or "DejaVu Sans"
    update_overlay()
end)

mp.register_script_message("set-size", function(size)
    font_size = tonumber(size) or 60
    update_overlay()
end)

mp.register_script_message("set-bg", function(color)
    bg_color = color or "0000FF"
    update_overlay()
end)

mp.register_script_message("set-text-color", function(color)
    text_color = color or "FFFFFF"
    update_overlay()
end)