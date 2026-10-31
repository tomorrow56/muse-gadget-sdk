# OPPO Reno3 A / Android 11のMuse接続診断

確認日: 2026-10-30。Android 11 / API 30、Muse 13.0.0.4.159。

## 確認した原因

nRF ConnectではBLE接続・ボンディング・サービス検出・機器情報の送受信に
成功した。Museでは接続、MTU 247への変更、サービス5件の取得後、
`AuraBleConnectionImpl.setNotificationsEnabled-BWLJW6A`内で
`NoSuchMethodError`が発生した。

呼び出している`BluetoothGatt.writeDescriptor(BluetoothGattDescriptor, byte[])`
はAPI 33で追加されたオーバーロードであり、API 30には存在しない。
この例外で接続処理が停止し、ESP32へペアリング要求が届かなかった。
[Android API資料](https://developer.android.com/reference/android/bluetooth/BluetoothGatt#writeDescriptor(android.bluetooth.BluetoothGattDescriptor,%20byte[]))

アプリ側で古いAndroid向けのAPI分岐が必要となる。この結果は上記の
端末・アプリ版での観測であり、Android 11全般がBLE非対応という意味ではない。
別途観測した一時的なGATT 133はBluetooth再起動後に解消した。
iOS版Museでは同じ実機のペアリング・Wi-Fi設定に成功した。

## 残している診断用設定

`CONFIG_HOMEHUB_BLE_DEVICE_INFO_ON_SUBSCRIBE`は既定で無効。
SpotPearプロファイルでは、調査時の設定を再現するため有効にしている。
通知購読後500 ms待って接続と未設定状態を確認し、公開機器情報を送信する。
暗号化やBOOT確認を省略する処理ではない。

このタイミング変更ではアプリのAPI例外は解消しなかった。
Android 11向け修正として扱わず、新たな調査が不要なら無効にできる。
端末識別子、資格情報、生ログ、バックアップはこの記録に含めていない。
