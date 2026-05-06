/*
 * 배미유니버스 — Arduino Leonardo HID 스케치
 *
 * Serial 명령 수신 → 마우스/키보드 HID 동작 실행
 *
 * 명령 목록:
 *   CLICK            좌클릭 1회
 *   DBLCLICK         좌클릭 2회 (더블클릭)
 *   KEY:<key>:<ms>   키 누름 후 ms 대기
 *                    예) KEY:F4:60  KEY:Enter:50
 *
 * 보드: Arduino Leonardo (USB HID 지원 필수)
 */

#include <Keyboard.h>
#include <Mouse.h>

String cmd = "";

void setup() {
  Serial.begin(9600);
  Keyboard.begin();
  Mouse.begin();
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      cmd.trim();
      if (cmd.length() > 0) {
        handleCmd(cmd);
      }
      cmd = "";
    } else {
      cmd += c;
    }
  }
}

void handleCmd(String s) {
  // ── CLICK ──────────────────────────
  if (s == "CLICK") {
    Mouse.click(MOUSE_LEFT);

  // ── DBLCLICK ───────────────────────
  } else if (s == "DBLCLICK") {
    Mouse.click(MOUSE_LEFT);
    delay(80);
    Mouse.click(MOUSE_LEFT);

  // ── KEY:<key>:<ms> ─────────────────
  } else if (s.startsWith("KEY:")) {
    int first  = s.indexOf(':');
    int second = s.indexOf(':', first + 1);
    String key = s.substring(first + 1, second);
    int    ms  = s.substring(second + 1).toInt();

    pressKey(key);
    if (ms > 0) delay(ms);
  }
}

void pressKey(String key) {
  // 기능키
  if      (key == "Enter")  { Keyboard.press(KEY_RETURN);      delay(30); Keyboard.release(KEY_RETURN); }
  else if (key == "Esc")    { Keyboard.press(KEY_ESC);         delay(30); Keyboard.release(KEY_ESC); }
  else if (key == "Tab")    { Keyboard.press(KEY_TAB);         delay(30); Keyboard.release(KEY_TAB); }
  else if (key == "Space")  { Keyboard.press(' ');             delay(30); Keyboard.release(' '); }
  else if (key == "Up")     { Keyboard.press(KEY_UP_ARROW);    delay(30); Keyboard.release(KEY_UP_ARROW); }
  else if (key == "Down")   { Keyboard.press(KEY_DOWN_ARROW);  delay(30); Keyboard.release(KEY_DOWN_ARROW); }
  else if (key == "Left")   { Keyboard.press(KEY_LEFT_ARROW);  delay(30); Keyboard.release(KEY_LEFT_ARROW); }
  else if (key == "Right")  { Keyboard.press(KEY_RIGHT_ARROW); delay(30); Keyboard.release(KEY_RIGHT_ARROW); }
  // F1~F12
  else if (key == "F1")  { Keyboard.press(KEY_F1);  delay(30); Keyboard.release(KEY_F1); }
  else if (key == "F2")  { Keyboard.press(KEY_F2);  delay(30); Keyboard.release(KEY_F2); }
  else if (key == "F3")  { Keyboard.press(KEY_F3);  delay(30); Keyboard.release(KEY_F3); }
  else if (key == "F4")  { Keyboard.press(KEY_F4);  delay(30); Keyboard.release(KEY_F4); }
  else if (key == "F5")  { Keyboard.press(KEY_F5);  delay(30); Keyboard.release(KEY_F5); }
  else if (key == "F6")  { Keyboard.press(KEY_F6);  delay(30); Keyboard.release(KEY_F6); }
  else if (key == "F7")  { Keyboard.press(KEY_F7);  delay(30); Keyboard.release(KEY_F7); }
  else if (key == "F8")  { Keyboard.press(KEY_F8);  delay(30); Keyboard.release(KEY_F8); }
  else if (key == "F9")  { Keyboard.press(KEY_F9);  delay(30); Keyboard.release(KEY_F9); }
  else if (key == "F10") { Keyboard.press(KEY_F10); delay(30); Keyboard.release(KEY_F10); }
  else if (key == "F11") { Keyboard.press(KEY_F11); delay(30); Keyboard.release(KEY_F11); }
  else if (key == "F12") { Keyboard.press(KEY_F12); delay(30); Keyboard.release(KEY_F12); }
  // 숫자/문자 단일키
  else if (key.length() == 1) {
    char c = key[0];
    Keyboard.press(c);
    delay(30);
    Keyboard.release(c);
  }
}
