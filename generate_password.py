import bcrypt
import getpass

def main():
    print("AI Shorts Generator - Password Generator")
    print("---------------------------------------")
    password = getpass.getpass("Enter your master password: ")
    confirm = getpass.getpass("Confirm password: ")
    
    if password != confirm:
        print("Passwords do not match!")
        return
        
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    
    # bcrypt returns bytes, decode to string for .env
    hash_str = hashed.decode('utf-8')
    
    print("\nAdd this to your .env file:")
    print(f"MASTER_PASSWORD_HASH={hash_str}")
    print("SECRET_KEY=yoursecretkeyhere (Use a long random string)")

if __name__ == "__main__":
    main()
