global _start

section .text

exit:
  mov ebx, eax
  mov eax, 1
  int 0x80

printchar:
  push ebp            ; save base pointer
  mov ebp, esp        ; set base pointer
  push ebx            ; save ebx

  mov ecx, ebp        ; set ecx to base pointer
  add ecx, 8          ; 8 bytes from base pointer
                      ; this is the first argument

  mov eax, 4          ; write
  mov ebx, 1          ; stdout
                      ; ecx already set
  mov edx, 1          ; length
  int 0x80

  pop ebx             ; restore ebx
  mov esp, ebp
  pop ebp
  ret

dividebyten:      ; divide eax by 10
                  ; eax is input, eax is output
                  ; edx is output remainder
  mov    ebx, 10
  mov    edx, 0       ; clear edx
  div    ebx          ; EDX:EAX / EBX = EAX remainder EDX
  ret

print_int:            ; print unsigned 32 bit integer
                      ; as decimal, removes leading zeroes
                      ; 1st argument is value to print
  ; prologue
  push ebp            ; save base pointer
  mov ebp, esp        ; set base pointer

  mov eax, [ebp+8]     ; read 1sr argument

  ; hack to prevent segmentation fault when value is zero
  ; -> why is there a segmentation fault?
  push   eax            ; save eax
  mov    ecx, 1
  cmp    eax, 0         ; check if digit count is zero
  je     print_int_loop2
  ;pop    eax            ; restore eax -> not needed ?

  ; check 1st bit from left for sign
  ; if set, print minus sign
  mov    ebx, eax
  shr    ebx, 31        ; shift right 31 bits
  jz     print_digit_count ; skip if positive
  push   eax            ; save eax
  push 45               ; ascii minus sign
  call   printchar
  add    esp, 4         ; clear stack
  pop    eax            ; restore eax

  not    eax            ; negate eax
  inc    eax            ; add 1

print_digit_count:
  mov    ecx, 10        ; digit count to produce
                        ; 10 digits in a 32 bit integer
                        ; max 4'294'967'295
                        ; 2'147'483'647 for signed integer
                        ; -2'147'483'648 for signed integer

print_int_loop:
  call   dividebyten    ; divide binary by 10, digit is
                        ; remainder in edx rest in eax
                        ; (reversed order)
  push   edx            ; push digit

  dec    ecx             ; decrement digit count
  jne    print_int_loop  ; loop until digit count is zero

  mov    ecx, 10         ; digit count to print
print_int_remove_leading_zeroes:
  pop    eax
                        ; check if digit is zero
                        ; if so, don't print
  dec    ecx
  cmp    eax, 0
  je    print_int_remove_leading_zeroes
  inc    ecx
  push   eax            ; push digit back on stack
print_int_loop2:
  pop    eax
  add    eax, 0x30      ; convert remainder to ascii
                        ; call routine
  push   ecx            ; save digit count
  push   eax            ; push ascii digit
  call   printchar
  add    esp, 4         ; clear stack
  pop    ecx            ; restore digit count

  dec    ecx
  jne    print_int_loop2

  ; epilogue
  mov esp, ebp
  pop ebp
  ret

_start:
  push ebp
  mov ebp, esp

  ;call block_0

  ; get literal
  mov eax, -0

  ; push result
  push eax

  ; print stack top
  call print_int
  add esp, 4      ; clear stack

  ; default exit
  mov eax, 0
  jmp exit
