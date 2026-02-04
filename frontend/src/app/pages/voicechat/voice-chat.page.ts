import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  Output,
  ViewChild,
  NgZone,
  OnInit,
  OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../../services/api.service'; // Adjust path
import { MessageService } from 'primeng/api';
import { Room, RoomEvent, RemoteTrack, RemoteParticipant, DataPacket_Kind } from 'livekit-client'; // ✅ Import LiveKit
import { HeaderComponent } from '../../shared/header/header.component';
interface ChatMessage {
  text: string;
  sender: 'user' | 'ai';
  time: Date;
}

declare var window: any;

@Component({
  selector: 'app-voice-chat',
  standalone: true,
  imports: [CommonModule, DialogModule, ButtonModule, HeaderComponent],
  templateUrl: './voice-chat.page.html',
  styleUrls: ['./voice-chat.page.scss'],
  providers: [MessageService],
})
export class VoiceChatComponent implements OnInit, OnDestroy {
  //   @Input() visible: boolean = false;
  //   @Output() visibleChange = new EventEmitter<boolean>();
  @ViewChild('chatContainer') private chatContainer!: ElementRef;

  messages: ChatMessage[] = [];
  statusText: string = 'กำลังเชื่อมต่อ...';

  // LiveKit Variables
  room!: Room;
  isListening: boolean = false;
  isProcessing: boolean = false;

  constructor(
    private api: ApiService,
    private ngZone: NgZone,
    private messageService: MessageService,
  ) {}

  async ngOnInit() {
    this.room = new Room({
      adaptiveStream: true,
      dynacast: true,
    });

    this.setupRoomEvents();
    await this.connectRoom();
  }

  ngOnDestroy() {
    this.room?.disconnect();
  }

  // เชื่อมต่อห้องเมื่อเปิด Dialog
  //   async openChat() {
  //     this.visible = true;
  //     this.visibleChange.emit(true);

  //     if (this.room.state === 'connected') return;

  //     try {
  //       this.statusText = 'กำลังขอ Token...';

  //       // 1. ขอ Token จาก Backend
  //       this.api.getLiveKitToken().subscribe({
  //         next: async (res) => {
  //           this.statusText = 'กำลังเข้าห้อง...';

  //           // 2. Connect LiveKit
  //           // ⚠️ ใส่ URL ของ LiveKit Cloud คุณที่นี่ (หรือดึงจาก env/api ก็ได้)
  //           const LIVEKIT_URL = 'wss://finalproject-lceiqqsp.livekit.cloud';
  //           console.log('Connecting to LiveKit at', res);
  //           await this.room.connect(LIVEKIT_URL, res.token);

  //           this.statusText = 'กดปุ่มไมค์เพื่อเริ่มคุย';
  //           console.log('room', this.room);
  //           console.log('Connected to Room:', this.room.name);

  //           // 3. เริ่มฟังเสียงจาก Agent (Audio Playback)
  //           this.room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
  //             if (track.kind === 'audio') {
  //               track.attach(); // เล่นเสียงอัตโนมัติ
  //             }
  //           });
  //         },
  //         error: (err) => {
  //           this.statusText = 'เชื่อมต่อไม่ได้';
  //           console.error(err);
  //         },
  //       });
  //     } catch (e) {
  //       console.error('Connection failed', e);
  //     }
  //   }

  setupRoomEvents() {
    this.room.on(RoomEvent.DataReceived, (payload, participant, kind) => {
      console.log('📩 RAW DATA RECEIVED', payload, participant?.identity, kind);
      const decoder = new TextDecoder();
      const strData = decoder.decode(payload);

      try {
        const data = JSON.parse(strData);

        this.ngZone.run(() => {
          if (data.type === 'user_text') {
            this.addMessage(data.text, 'user');

            // ✅ เมื่อ User พูดจบ -> เริ่มแสดงสถานะ "กำลังคิด..."
            this.isProcessing = true;
            this.statusText = 'กำลังประมวลผล...';
          } else if (data.type === 'agent_text') {
            // ✅ เมื่อ Agent ตอบกลับ -> ปิดสถานะ "กำลังคิด..."
            this.isProcessing = false;

            this.addMessage(data.text, 'ai');
            this.statusText = 'กำลังพูด...';
          }
        });
      } catch (e) {
        console.error('Parse data error', e);
      }
    });

    this.room.on(RoomEvent.Disconnected, () => {
      this.statusText = 'จบการสนทนา';
      this.isListening = false;
      this.isProcessing = false;
    });
    this.room.on(RoomEvent.LocalTrackPublished, (publication, participant) => {
      console.log('✅ My Microphone Track Published:', publication.track?.sid);
    });

    // ✅ 2. เช็คว่า LiveKit ได้ยินเสียงเราไหม (Active Speaker)
    this.room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      // speakers คือ list ของคนที่กำลังพูดอยู่
      const isMeSpeaking = speakers.some((s) => s.identity === this.room.localParticipant.identity);

      if (isMeSpeaking) {
        console.log(this.room.localParticipant.identity, 'is speaking');
        console.log('🔊 Detected voice activity (LiveKit hears you!)');
        // คุณอาจจะเพิ่ม UI indicator เล็กๆ ตรงนี้เพื่อให้ user รู้ว่าไมค์ดัง
      }
    });

    // ✅ 3. เช็ค Error เกี่ยวกับ Media Device
    this.room.on(RoomEvent.MediaDevicesError, (e) => {
      console.error('❌ Media Device Error:', e);
      this.statusText = 'ไม่สามารถเข้าถึงไมโครโฟนได้';
    });
  }

  async toggleSpeech() {
    if (!this.room || this.room.state !== 'connected') {
      console.warn('Room not connected yet');
      this.statusText = 'ยังไม่เชื่อมต่อห้อง';
      return;
    }

    this.isListening = !this.isListening;

    try {
      await this.room.localParticipant.setMicrophoneEnabled(this.isListening);

      this.statusText = this.isListening ? 'กำลังฟังคุณพูด... 👂' : 'ไมค์ปิดอยู่';
    } catch (err) {
      console.error('Toggle mic failed', err);
      this.statusText = 'ไม่สามารถเปิดไมค์ได้';
    }
  }

  //   closeChat() {
  //     this.visible = false;
  //     this.visibleChange.emit(false);

  //     // ปิดไมค์แต่ยังไม่ต้อง Disconnect ห้องก็ได้ (เพื่อให้เปิดใหม่แล้วคุยต่อได้เลยเร็วๆ)
  //     // หรือจะ disconnect เลยก็ได้ตามชอบ
  //     if (this.isListening) {
  //       this.toggleSpeech();
  //     }
  //   }

  addMessage(text: string, sender: 'user' | 'ai') {
    this.messages.push({ text, sender, time: new Date() });
    setTimeout(() => {
      const container = this.chatContainer.nativeElement;
      container.scrollTop = container.scrollHeight;
    }, 100);
  }

  async connectRoom() {
    this.statusText = 'กำลังเชื่อมต่อ...';

    this.api.getLiveKitToken().subscribe({
      next: async (res) => {
        const LIVEKIT_URL = 'wss://finalproject-lceiqqsp.livekit.cloud';
        await this.room.connect(LIVEKIT_URL, res.token);

        this.statusText = 'กดปุ่มไมค์เพื่อเริ่มคุย';

        this.room.on(RoomEvent.TrackSubscribed, (track) => {
          if (track.kind === 'audio') {
            track.attach();
          }
        });
      },
      error: () => {
        this.statusText = 'เชื่อมต่อไม่ได้';
      },
    });
  }
}
